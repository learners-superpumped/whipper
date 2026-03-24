#!/bin/bash
# API key ping test — verifies keys actually work
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$PLUGIN_ROOT/scripts/core/api-keys.sh"

echo "=== API Key Verification ==="

# Gemini
GEMINI_KEY=$(get_api_key gemini 2>/dev/null || true)
if [[ -n "$GEMINI_KEY" ]]; then
  echo -n "  Gemini: "
  RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_KEY")
  [[ "$RESP" == "200" ]] && echo "✅ OK" || echo "❌ HTTP $RESP"
else
  echo "  Gemini: ⚠️  Not configured"
fi

# OpenAI
OPENAI_KEY=$(get_api_key openai 2>/dev/null || true)
if [[ -n "$OPENAI_KEY" ]]; then
  echo -n "  OpenAI: "
  RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $OPENAI_KEY" \
    "https://api.openai.com/v1/models")
  [[ "$RESP" == "200" ]] && echo "✅ OK" || echo "❌ HTTP $RESP"
else
  echo "  OpenAI: ⚠️  Not configured"
fi
