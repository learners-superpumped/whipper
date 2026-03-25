#!/bin/bash
# Whipper Stop Hook — blocks exit on status: failed, allows on status: passed
set -euo pipefail
export LC_ALL=en_US.UTF-8

HOOK_INPUT=$(cat)
STATE_FILE=".claude/whipper.local.md"

# No state file → allow exit
[[ ! -f "$STATE_FILE" ]] && exit 0

# Parse YAML frontmatter
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$STATE_FILE")
ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
SKILL=$(echo "$FRONTMATTER" | grep '^skill:' | sed 's/skill: *//' | sed 's/^"\(.*\)"$/\1/')
STATUS=$(echo "$FRONTMATTER" | grep '^status:' | sed 's/status: *//' | sed 's/^"\(.*\)"$/\1/')
TASK_DIR=$(echo "$FRONTMATTER" | grep '^task_dir:' | sed 's/task_dir: *//' | sed 's/^"\(.*\)"$/\1/')
TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/' || true)
FINAL_STATUS_FILE="${TASK_DIR}/.final_status"

find_iteration_file() {
  local iteration="$1"
  local suffix="$2"
  local padded="${TASK_DIR}/iterations/$(printf '%02d' "$iteration")-${suffix}"
  local plain="${TASK_DIR}/iterations/${iteration}-${suffix}"

  if [[ -f "$padded" ]]; then
    printf '%s\n' "$padded"
    return 0
  fi
  if [[ -f "$plain" ]]; then
    printf '%s\n' "$plain"
    return 0
  fi
  return 1
}

# Session isolation
STATE_SESSION=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/' || true)
HOOK_SESSION=$(echo "$HOOK_INPUT" | jq -r '.session_id // ""')
if [[ -n "$STATE_SESSION" ]] && [[ "$STATE_SESSION" != "$HOOK_SESSION" ]]; then
  exit 0
fi

# Validate numeric fields
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]] || [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "⚠️  Whipper: State file corrupted. Stopping." >&2
  rm "$STATE_FILE"
  exit 0
fi

# PLUGIN_ROOT (needed by both passed and failed paths)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Status: passed → allow exit, update global index
if [[ "$STATUS" == "passed" ]]; then
  # Source logger and update global index
  source "$PLUGIN_ROOT/scripts/core/logger.sh"
  [[ -z "$TASK_ID" ]] && TASK_ID=$(basename "$TASK_DIR" | sed 's/^whipper-//')
  update_global_index "$TASK_ID" "passed" "$ITERATION"
  printf '%s\n' "passed" > "$FINAL_STATUS_FILE"
  rm "$STATE_FILE"
  exit 0
fi

# Max iterations reached → allow exit with warning
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  echo "🛑 Whipper: Max iterations ($MAX_ITERATIONS) reached."
  source "$PLUGIN_ROOT/scripts/core/logger.sh"
  [[ -z "$TASK_ID" ]] && TASK_ID=$(basename "$TASK_DIR" | sed 's/^whipper-//')
  update_global_index "$TASK_ID" "max_iterations" "$ITERATION"
  printf '%s\n' "max_iterations" > "$FINAL_STATUS_FILE"
  rm "$STATE_FILE"
  exit 0
fi

# Status: failed or running → block and re-inject
NEXT_ITERATION=$((ITERATION + 1))

# Notion에 현재 iteration 로그 업로드 (비동기, 실패해도 무시)
NOTION_PAGE_ID=$(echo "$FRONTMATTER" | grep '^notion_page_id:' | sed 's/notion_page_id: *//' | sed 's/^"\(.*\)"$/\1/')
if [[ -z "$NOTION_PAGE_ID" ]] && [[ -f "$TASK_DIR/.notion_page_id" ]]; then
  NOTION_PAGE_ID=$(cat "$TASK_DIR/.notion_page_id")
fi
if [[ -n "$NOTION_PAGE_ID" ]] && [[ -d "$TASK_DIR/iterations" ]]; then
  python3 "$PLUGIN_ROOT/scripts/notion/upload_task.py" "$NOTION_PAGE_ID" "$TASK_DIR" --iteration "$ITERATION" 2>/dev/null &
fi

# Extract prompt (everything after closing ---)
PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$STATE_FILE")
if [[ -z "$PROMPT_TEXT" ]]; then
  echo "⚠️  Whipper: No prompt in state file. Stopping." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Read latest manager eval for feedback (if exists)
EVAL_FILE="$(find_iteration_file "$ITERATION" "manager-eval.md" || true)"
FEEDBACK=""
if [[ -n "$EVAL_FILE" ]] && [[ -f "$EVAL_FILE" ]]; then
  FEEDBACK=$(cat "$EVAL_FILE")
fi

# Read latest executor log
LOG_FILE="$(find_iteration_file "$ITERATION" "executor-log.md" || true)"
EXEC_LOG=""
if [[ -n "$LOG_FILE" ]] && [[ -f "$LOG_FILE" ]]; then
  EXEC_LOG=$(cat "$LOG_FILE")
fi

# Update iteration in state file
TEMP_FILE="${STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE" | \
  sed "s/^status: .*/status: running/" > "$TEMP_FILE"
mv "$TEMP_FILE" "$STATE_FILE"

# Build re-injection reason
REASON="$PROMPT_TEXT"
if [[ -n "$FEEDBACK" ]]; then
  REASON="$REASON

## 이전 iteration Manager 평가
$FEEDBACK"
fi
if [[ -n "$EXEC_LOG" ]]; then
  REASON="$REASON

## 이전 iteration Executor 로그
$EXEC_LOG"
fi

SYSTEM_MSG="🔄 Whipper iteration $NEXT_ITERATION/$MAX_ITERATIONS | skill: $SKILL"

jq -n \
  --arg prompt "$REASON" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
