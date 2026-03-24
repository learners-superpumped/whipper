#!/bin/bash
# Core integration test — setup, state file, logging, stop hook
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

check() {
  local name="$1" cond="$2"
  if eval "$cond"; then
    echo "  ✅ $name"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Test: setup.sh ==="

# Clean up
rm -rf .claude/whipper.local.md .whipper/tasks/

# Run setup
export CLAUDE_CODE_SESSION_ID="test-session-123"
bash "$PLUGIN_ROOT/scripts/core/setup.sh" --skill whip --max-iterations 5 "테스트 명령어" > /dev/null

check "State file created" "[[ -f .claude/whipper.local.md ]]"
check "Task folder created" "[[ -d .whipper/tasks/ ]]"
check "Task has iterations dir" "ls .whipper/tasks/*/iterations/ > /dev/null 2>&1"
check "Task has deliverables dir" "ls .whipper/tasks/*/deliverables/ > /dev/null 2>&1"
check "Task has resources dir" "ls .whipper/tasks/*/resources/ > /dev/null 2>&1"
check "State file has iteration: 1" "grep -q 'iteration: 1' .claude/whipper.local.md"
check "State file has max_iterations: 5" "grep -q 'max_iterations: 5' .claude/whipper.local.md"
check "State file has skill: whip" "grep -q 'skill: whip' .claude/whipper.local.md"
check "State file has status: running" "grep -q 'status: running' .claude/whipper.local.md"
check "State file has session_id" "grep -q 'session_id: test-session-123' .claude/whipper.local.md"
check "State file has prompt" "grep -q '테스트 명령어' .claude/whipper.local.md"
check "Global index updated" "jq -e '.[-1].skill == \"whip\"' ~/.claude/whipper-logs/index.json > /dev/null"

echo ""
echo "=== Test: api-keys.sh ==="

source "$PLUGIN_ROOT/scripts/core/api-keys.sh"

export WHIPPER_GEMINI_API_KEY="test-key-123"
check "get_api_key primary" "[[ \$(get_api_key gemini) == 'test-key-123' ]]"

unset WHIPPER_GEMINI_API_KEY
export GEMINI_API_KEY="fallback-key-456"
check "get_api_key fallback" "[[ \$(get_api_key gemini) == 'fallback-key-456' ]]"

unset GEMINI_API_KEY
check "get_api_key missing" "! get_api_key gemini 2>/dev/null"

echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

# Cleanup
rm -rf .claude/whipper.local.md .whipper/tasks/

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
