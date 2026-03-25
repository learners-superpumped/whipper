---
description: "Review Notion todo list, run queued projects, check blocked items"
argument-hint: "[--dry-run]"
allowed-tools: [
  "Read",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)"
]
---

# Whip Todo — Notion 프로젝트 큐 관리

## Step 1: Run the headless todo helper

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/daemon/todo_once.py" $ARGUMENTS`

## Step 2: Summarize

- `--dry-run`이면 follow-up 후보와 예정 액션만 요약한다
- 그 외에는 실제 follow-up 디스패치/동기화 결과를 요약한다
- 이 명령은 Slack/Notion MCP를 직접 쓰지 않고, 데몬이 쓰는 동일한 REST/API 경로를 재사용한다
