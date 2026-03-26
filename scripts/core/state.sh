#!/bin/bash
# Whipper state helper — update/delete the state file without making Claude edit it directly.
set -euo pipefail
export LC_ALL=en_US.UTF-8

resolve_state_file() {
  if [[ -n "${WHIPPER_STATE_FILE:-}" ]]; then
    printf '%s\n' "$WHIPPER_STATE_FILE"
    return
  fi

  if [[ -f "$HOME/.claude/whipper.local.md" ]]; then
    printf '%s\n' "$HOME/.claude/whipper.local.md"
    return
  fi

  if [[ -f ".claude/whipper.local.md" ]]; then
    printf '%s\n' ".claude/whipper.local.md"
    return
  fi

  printf '%s\n' "$HOME/.claude/whipper.local.md"
}

STATE_FILE=$(resolve_state_file)
COMMAND="${1:-}"

usage() {
  cat <<'EOF' >&2
Usage:
  state.sh get KEY
  state.sh set KEY VALUE
  state.sh delete
EOF
  exit 1
}

[[ -z "$COMMAND" ]] && usage

case "$COMMAND" in
  get)
    KEY="${2:-}"
    [[ -z "$KEY" ]] && usage
    [[ -f "$STATE_FILE" ]] || exit 1
    python3 - "$STATE_FILE" "$KEY" <<'PY'
import re
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
key = sys.argv[2]
text = state_file.read_text()
match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
if not match:
    sys.exit(1)
value = match.group(1).strip()
if value.startswith('"') and value.endswith('"'):
    value = value[1:-1]
print(value)
PY
    ;;
  set)
    KEY="${2:-}"
    VALUE="${3-}"
    [[ -z "$KEY" ]] && usage
    [[ -f "$STATE_FILE" ]] || { echo "State file not found: $STATE_FILE" >&2; exit 1; }
    python3 - "$STATE_FILE" "$KEY" "$VALUE" <<'PY'
import re
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
text = state_file.read_text()

if not value or re.fullmatch(r"-?\d+", value):
    rendered = value
else:
    rendered = f'"{value}"'

pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", flags=re.MULTILINE)
replacement = f"{key}: {rendered}"

if pattern.search(text):
    updated = pattern.sub(replacement, text, count=1)
else:
    marker = "---\n"
    if marker in text:
        updated = text.replace(marker, f"{marker}{replacement}\n", 1)
    else:
        updated = f"{replacement}\n{text}"

state_file.write_text(updated)
PY
    ;;
  delete)
    rm -f "$STATE_FILE"
    ;;
  *)
    usage
    ;;
esac
