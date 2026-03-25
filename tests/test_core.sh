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
rm -rf .claude/whipper.local.md /tmp/whipper-*-테스트*

# Run setup
export CLAUDE_CODE_SESSION_ID="test-session-123"
bash "$PLUGIN_ROOT/scripts/core/setup.sh" --skill whip --max-iterations 5 "테스트 명령어" > /dev/null

# Extract task_dir from state file
TASK_DIR=$(grep '^task_dir:' .claude/whipper.local.md | sed 's/task_dir: *//' | sed 's/^"\(.*\)"$/\1/')

check "State file created" "[[ -f .claude/whipper.local.md ]]"
check "Task folder in /tmp/" "[[ -d \$TASK_DIR ]]"
check "Task dir starts with /tmp/whipper-" "[[ \$TASK_DIR == /tmp/whipper-* ]]"
check "Task has iterations dir" "[[ -d \$TASK_DIR/iterations ]]"
check "Task has deliverables dir" "[[ -d \$TASK_DIR/deliverables ]]"
check "Task has resources dir" "[[ -d \$TASK_DIR/resources ]]"
check "State file has iteration: 1" "grep -q 'iteration: 1' .claude/whipper.local.md"
check "State file has max_iterations: 5" "grep -q 'max_iterations: 5' .claude/whipper.local.md"
check "State file has skill: whip" "grep -q 'skill: whip' .claude/whipper.local.md"
check "State file has status: running" "grep -q 'status: running' .claude/whipper.local.md"
check "State file has session_id" "grep -q 'session_id: test-session-123' .claude/whipper.local.md"
check "State file has task_id" "grep -q 'task_id:' .claude/whipper.local.md"
check "State file has notion_page_id" "grep -q 'notion_page_id:' .claude/whipper.local.md"
check "State file has prompt" "grep -q '테스트 명령어' .claude/whipper.local.md"
check "Global index updated" "jq -e '.[-1].skill == \"whip\"' ~/.claude/whipper-logs/index.json > /dev/null"
check "Global index stores task path" "jq -e --arg path \"$TASK_DIR\" '.[-1].path == \$path' ~/.claude/whipper-logs/index.json > /dev/null"

echo ""
echo "=== Test: setup.sh Slack task id ==="

rm -rf .claude/whipper.local.md /tmp/whipper-*C0TEST*
export WHIPPER_NOTION_PAGE_ID="page-abc"
export WHIPPER_THREAD_PAGE_MODE="existing"
export WHIPPER_THREAD_PAGE_NAME="기존 작업"
export WHIPPER_THREAD_PAGE_ITERATION="4"
export WHIPPER_THREAD_PAGE_STATUS="진행중"
export GEMINI_API_KEY="test-gemini-key"
export CALLME_OPENAI_API_KEY="test-openai-key"
bash "$PLUGIN_ROOT/scripts/core/setup.sh" --skill whip-think "[Slack thread: C0TEST/1774434726.092599] /think 17이 소수인지 한 줄로 답해줘" > /dev/null
unset WHIPPER_NOTION_PAGE_ID WHIPPER_THREAD_PAGE_MODE WHIPPER_THREAD_PAGE_NAME WHIPPER_THREAD_PAGE_ITERATION WHIPPER_THREAD_PAGE_STATUS
unset GEMINI_API_KEY CALLME_OPENAI_API_KEY
SLACK_TASK_DIR=$(grep '^task_dir:' .claude/whipper.local.md | sed 's/task_dir: *//' | sed 's/^"\(.*\)"$/\1/')

check "Slack task dir includes full thread ts" "[[ \$SLACK_TASK_DIR == *1774434726092599* ]]"
check "Slack task dir includes command slug" "[[ \$SLACK_TASK_DIR == *17이-소수인지-한-줄로-답해줘* ]]"
check "State file keeps pre-resolved notion_page_id" "grep -q 'notion_page_id: \"page-abc\"' .claude/whipper.local.md"
check "State file keeps thread_page_mode" "grep -q 'thread_page_mode: \"existing\"' .claude/whipper.local.md"
check "State file keeps thread_page_iteration" "grep -q 'thread_page_iteration: 4' .claude/whipper.local.md"

echo ""
echo "=== Test: Slack post wrapper ==="

WRAPPER_TASK_DIR="/tmp/whipper-wrapper-test"
rm -rf "$WRAPPER_TASK_DIR"
bash "$PLUGIN_ROOT/post.sh" "$WRAPPER_TASK_DIR" "C0TEST" "1774434726.092599" "wrapper works"
check "Root post.sh wrapper writes slack message" "ls \$WRAPPER_TASK_DIR/slack_messages/*.json >/dev/null 2>&1"
check "Wrapped Slack message contains text" "grep -q 'wrapper works' \$WRAPPER_TASK_DIR/slack_messages/*.json"

echo ""
echo "=== Test: state.sh ==="

bash "$PLUGIN_ROOT/scripts/core/state.sh" set notion_page_id "page-123"
check "state.sh set quoted value" "grep -q 'notion_page_id: \"page-123\"' .claude/whipper.local.md"

bash "$PLUGIN_ROOT/scripts/core/state.sh" set iteration "4"
check "state.sh set numeric value" "grep -q 'iteration: 4' .claude/whipper.local.md"

STATE_ITERATION=$(bash "$PLUGIN_ROOT/scripts/core/state.sh" get iteration)
check "state.sh get value" "[[ \$STATE_ITERATION == 4 ]]"

echo ""
echo "=== Test: api-keys.sh ==="

source "$PLUGIN_ROOT/scripts/core/api-keys.sh"

export WHIPPER_GEMINI_API_KEY="test-key-123"
check "get_api_key primary" "[[ \$(get_api_key gemini) == 'test-key-123' ]]"

unset WHIPPER_GEMINI_API_KEY
export GEMINI_API_KEY="fallback-key-456"
check "get_api_key fallback" "[[ \$(get_api_key gemini) == 'fallback-key-456' ]]"

unset GEMINI_API_KEY
EMPTY_SETTINGS=$(mktemp)
cat > "$EMPTY_SETTINGS" <<'EOF'
{
  "env": {}
}
EOF
export WHIPPER_SETTINGS_FILE="$EMPTY_SETTINGS"
check "get_api_key missing" "! get_api_key gemini >/dev/null 2>&1"
rm -f "$EMPTY_SETTINGS"

TEMP_SETTINGS=$(mktemp)
cat > "$TEMP_SETTINGS" <<'EOF'
{
  "env": {
    "CALLME_OPENAI_API_KEY": "settings-openai",
    "GEMINI_API_KEY": "settings-gemini"
  }
}
EOF
export WHIPPER_SETTINGS_FILE="$TEMP_SETTINGS"
check "get_api_key settings fallback gemini" "[[ \$(get_api_key gemini) == 'settings-gemini' ]]"
check "get_api_key settings fallback openai" "[[ \$(get_api_key openai) == 'settings-openai' ]]"
unset WHIPPER_SETTINGS_FILE
rm -f "$TEMP_SETTINGS"

echo ""
echo "=== Test: stop-hook completion bookkeeping ==="

rm -f .claude/whipper.local.md
export CLAUDE_CODE_SESSION_ID="hook-session-456"
bash "$PLUGIN_ROOT/scripts/core/setup.sh" --skill whip "완료 테스트" > /dev/null
HOOK_TASK_DIR=$(grep '^task_dir:' .claude/whipper.local.md | sed 's/task_dir: *//' | sed 's/^"\(.*\)"$/\1/')
HOOK_TASK_ID=$(grep '^task_id:' .claude/whipper.local.md | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/')
bash "$PLUGIN_ROOT/scripts/core/state.sh" set status passed
printf '{"session_id":"hook-session-456"}' | bash "$PLUGIN_ROOT/hooks/stop-hook.sh" > /dev/null

check "Stop hook removes state file on pass" "[[ ! -f .claude/whipper.local.md ]]"
check "Stop hook writes final status marker" "grep -q '^passed$' \"$HOOK_TASK_DIR/.final_status\""
check "Stop hook updates global index result with task_id" "jq -e --arg id \"$HOOK_TASK_ID\" 'map(select(.id == \$id))[0].result == \"passed\"' ~/.claude/whipper-logs/index.json > /dev/null"

echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

# Cleanup
bash "$PLUGIN_ROOT/scripts/core/state.sh" delete || true
rm -rf /tmp/whipper-*-테스트* /tmp/whipper-*C0TEST*
rm -rf "$WRAPPER_TASK_DIR"

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
