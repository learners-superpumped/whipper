#!/bin/bash
# API Key resolver — source this file, then call get_api_key "openai"
set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$SCRIPT_SOURCE")/../.." && pwd)}"
API_KEYS_CONFIG="$PLUGIN_ROOT/config/api-keys.json"

resolve_settings_file() {
  printf '%s\n' "${WHIPPER_SETTINGS_FILE:-$HOME/.claude/settings.json}"
}

get_settings_env_value() {
  local key="$1"
  local settings_file
  settings_file="$(resolve_settings_file)"
  python3 - "$settings_file" "$key" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
key = sys.argv[2]
if not path.exists():
    sys.exit(1)

try:
    data = json.loads(path.read_text())
except Exception:
    sys.exit(1)

env = data.get("env", {}) if isinstance(data, dict) else {}
value = env.get(key) if isinstance(env, dict) else None
if not value:
    sys.exit(1)
print(value)
PY
}

get_api_key() {
  local name="$1"
  local env_var fallback value

  env_var=$(jq -r --arg n "$name" '.[$n].env_var // ""' "$API_KEYS_CONFIG")
  fallback=$(jq -r --arg n "$name" '.[$n].fallback // ""' "$API_KEYS_CONFIG")

  # Try primary
  value="${!env_var:-}"
  [[ -n "$value" ]] && echo "$value" && return 0

  # Try fallback
  if [[ -n "$fallback" ]]; then
    value="${!fallback:-}"
    [[ -n "$value" ]] && echo "$value" && return 0
  fi

  # Try ~/.claude/settings.json env section
  if [[ -n "$env_var" ]]; then
    value="$(get_settings_env_value "$env_var" 2>/dev/null || true)"
    [[ -n "$value" ]] && echo "$value" && return 0
  fi
  if [[ -n "$fallback" ]]; then
    value="$(get_settings_env_value "$fallback" 2>/dev/null || true)"
    [[ -n "$value" ]] && echo "$value" && return 0
  fi

  echo "❌ API key '$name' not found. Set $env_var or $fallback in settings.json env." >&2
  return 1
}

check_required_keys() {
  local skill="$1"
  local missing=()

  for name in $(jq -r 'to_entries[] | select(.value.required_by | index($skill)) | .key' --arg skill "$skill" "$API_KEYS_CONFIG"); do
    if ! get_api_key "$name" > /dev/null 2>&1; then
      missing+=("$name")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "❌ Missing API keys for $skill: ${missing[*]}" >&2
    echo "   Set them in ~/.claude/settings.json env section." >&2
    return 1
  fi
}
