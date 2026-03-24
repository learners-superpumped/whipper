#!/bin/bash
# Whipper Setup Script — creates state file + task folder
set -euo pipefail
export LC_ALL=en_US.UTF-8

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

# Generate task slug from prompt (first 30 chars, sanitized)
SLUG=$(printf '%s' "$PROMPT" | cut -c1-30 | sed 's/[^a-zA-Z0-9가-힣]/-/g' | sed 's/--*/-/g' | sed 's/-$//')
DATE=$(date +%Y-%m-%d)
TASK_DIR=".whipper/tasks/${DATE}-${SLUG}"

# Create task folder structure
mkdir -p "$TASK_DIR/iterations" "$TASK_DIR/deliverables" "$TASK_DIR/resources"

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
task_dir: "$TASK_DIR"
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
jq --arg id "${DATE}-${SLUG}" \
   --arg cmd "$PROMPT" \
   --arg skill "$SKILL" \
   --arg project "$PWD" \
   --arg path "$PWD/$TASK_DIR" \
   --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '. += [{id: $id, command: $cmd, skill: $skill, project: $project, path: $path, started_at: $started, finished_at: null, iterations: 0, result: "running"}]' \
   "$GLOBAL_INDEX" > "$TEMP" && mv "$TEMP" "$GLOBAL_INDEX"

# Output
cat <<EOF
🔥 Whipper activated!

Skill: $SKILL
Task: $TASK_DIR
Iteration: 1
Max iterations: $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo "unlimited"; fi)

$PROMPT
EOF
