#!/bin/bash
# Logger utility — writes to task iteration files and updates global index
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Update global index entry on completion
update_global_index() {
  local task_id="$1"
  local result="$2"
  local iterations="$3"
  local global_index="$HOME/.claude/whipper-logs/index.json"

  [[ ! -f "$global_index" ]] && return 0

  local temp=$(mktemp)
  jq --arg id "$task_id" \
     --arg result "$result" \
     --argjson iters "$iterations" \
     --arg finished "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     'map(if .id == $id then . + {result: $result, iterations: $iters, finished_at: $finished} else . end)' \
     "$global_index" > "$temp" && mv "$temp" "$global_index"
}
