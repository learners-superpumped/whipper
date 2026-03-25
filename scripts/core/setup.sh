#!/bin/bash
# Whipper Setup Script — creates state file + task folder
set -euo pipefail
export LC_ALL=en_US.UTF-8

sanitize_slug() {
  printf '%s' "$1" \
    | sed 's/[^a-zA-Z0-9가-힣]/-/g' \
    | sed 's/--*/-/g' \
    | sed 's/^-//' \
    | sed 's/-$//'
}

hash_prompt() {
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  else
    python3 - "$1" <<'PY'
import hashlib
import sys

print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())
PY
  fi
}

yaml_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

# Parse arguments (same pattern as ralph-loop)
PROMPT_PARTS=()
MAX_ITERATIONS=10
SKILL="whip"

while [[ $# -gt 0 ]]; do
  case $1 in
    --max-iterations)
      [[ -z "${2:-}" ]] && echo "❌ --max-iterations requires a number" >&2 && exit 1
      [[ ! "$2" =~ ^[0-9]+$ ]] && echo "❌ --max-iterations must be integer, got: $2" >&2 && exit 1
      MAX_ITERATIONS="$2"; shift 2 ;;
    --skill)
      SKILL="$2"; shift 2 ;;
    --notion)
      # Pass through for whip-learn
      PROMPT_PARTS+=("--notion"); shift ;;
    *)
      PROMPT_PARTS+=("$1"); shift ;;
  esac
done

PROMPT="${PROMPT_PARTS[*]:-}"

# Handle --max-iterations embedded in prompt (when $ARGUMENTS was quoted as single string)
if [[ "$PROMPT" =~ --max-iterations[[:space:]]+([0-9]+) ]]; then
  MAX_ITERATIONS="${BASH_REMATCH[1]}"
  PROMPT="${PROMPT/--max-iterations ${BASH_REMATCH[1]}/}"
  PROMPT="$(echo "$PROMPT" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')"
fi

# Handle --notion embedded in prompt
if [[ "$PROMPT" == *"--notion"* ]]; then
  PROMPT="${PROMPT/--notion/}"
  PROMPT="$(echo "$PROMPT" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')"
fi

[[ -z "$PROMPT" ]] && echo "❌ No prompt provided" >&2 && exit 1

if [[ "$SKILL" == "whip-think" || "$SKILL" == "whip-research" ]]; then
  # DESIGN.md baseline: think/research must run all configured external LLMs.
  # Fail fast here instead of silently degrading to a different skill shape.
  # shellcheck disable=SC1091
  source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}/scripts/core/api-keys.sh"
  check_required_keys "$SKILL"
fi

DATE=$(date +%Y-%m-%d)
PROMPT_HASH=$(hash_prompt "$PROMPT" | cut -c1-10)

if [[ "$PROMPT" =~ ^\[Slack\ thread:\ ([^/]+)/([0-9]+\.[0-9]+)\][[:space:]]*(.*)$ ]]; then
  SLACK_CHANNEL=$(sanitize_slug "${BASH_REMATCH[1]}")
  SLACK_THREAD=$(printf '%s' "${BASH_REMATCH[2]}" | tr -d '.')
  BODY_SLUG=$(sanitize_slug "$(printf '%s' "${BASH_REMATCH[3]}" | cut -c1-40)")
  [[ -z "$BODY_SLUG" ]] && BODY_SLUG="task"
  TASK_ID="${DATE}-slack-${SLACK_CHANNEL}-${SLACK_THREAD}-${BODY_SLUG}-${PROMPT_HASH}"
else
  SLUG=$(sanitize_slug "$(printf '%s' "$PROMPT" | cut -c1-40)")
  [[ -z "$SLUG" ]] && SLUG="task"
  TASK_ID="${DATE}-${SLUG}-${PROMPT_HASH}"
fi

TASK_DIR="/tmp/whipper-${TASK_ID}"
NOTION_PAGE_ID="${WHIPPER_NOTION_PAGE_ID:-}"
THREAD_PAGE_MODE="${WHIPPER_THREAD_PAGE_MODE:-unknown}"
THREAD_PAGE_NAME="$(yaml_escape "${WHIPPER_THREAD_PAGE_NAME:-}")"
THREAD_PAGE_ITERATION="${WHIPPER_THREAD_PAGE_ITERATION:-0}"
THREAD_PAGE_STATUS="$(yaml_escape "${WHIPPER_THREAD_PAGE_STATUS:-}")"

# Create task folder structure (in /tmp/, cleaned up on completion)
mkdir -p "$TASK_DIR/iterations" "$TASK_DIR/deliverables" "$TASK_DIR/resources" "$TASK_DIR/slack_messages"

# Create state file
mkdir -p .claude
cat > .claude/whipper.local.md <<EOF
---
active: true
skill: $SKILL
iteration: 1
max_iterations: $MAX_ITERATIONS
session_id: ${CLAUDE_CODE_SESSION_ID:-}
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
task_id: "$TASK_ID"
task_dir: "$TASK_DIR"
notion_page_id: "$(yaml_escape "$NOTION_PAGE_ID")"
thread_page_mode: "$THREAD_PAGE_MODE"
thread_page_name: "$THREAD_PAGE_NAME"
thread_page_iteration: $THREAD_PAGE_ITERATION
thread_page_status: "$THREAD_PAGE_STATUS"
status: running
---

$PROMPT
EOF

# Create global index directory
GLOBAL_INDEX="$HOME/.claude/whipper-logs/index.json"
mkdir -p "$(dirname "$GLOBAL_INDEX")"
[[ ! -f "$GLOBAL_INDEX" ]] && echo "[]" > "$GLOBAL_INDEX"

# Append entry to global index
TEMP=$(mktemp)
jq --arg id "$TASK_ID" \
   --arg cmd "$PROMPT" \
   --arg skill "$SKILL" \
   --arg project "$PWD" \
   --arg path "$TASK_DIR" \
   --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '. += [{id: $id, command: $cmd, skill: $skill, project: $project, path: $path, started_at: $started, finished_at: null, iterations: 0, result: "running"}]' \
   "$GLOBAL_INDEX" > "$TEMP" && mv "$TEMP" "$GLOBAL_INDEX"

# Output
cat <<EOF
🔥 Whipper activated!

Skill: $SKILL
Task ID: $TASK_ID
Iteration: 1
Max iterations: $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo "unlimited"; fi)

$PROMPT
EOF
