#!/bin/bash
# API Key resolver — source this file, then call get_api_key "openai"
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
API_KEYS_CONFIG="$PLUGIN_ROOT/config/api-keys.json"

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
