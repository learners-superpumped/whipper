---
description: "Review Notion todo list, run queued projects, check blocked items"
argument-hint: "[--dry-run]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)",
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-update-page",
  "mcp__claude_ai_Slack__slack_send_message",
  "mcp__claude_ai_Slack__slack_read_thread",
  "WebSearch",
  "WebFetch"
]
---

# Whip Todo — Notion 프로젝트 큐 관리

## Step 1: 현황 파악

1. Read config/notion.json에서 database_id 확인
2. database_id가 비어있으면: "Notion DB 미설정. /whipper:whip-notion-init을 먼저 실행하세요." 출력 후 종료
3. notion-query-database-view로 전체 프로젝트 조회
4. 상태별 집계 출력:
   ```
   📋 Whipper Todo 현황
   진행예정: N개 | 진행중: N개 | 블락드: N개 | 완료: N개 | 드랍: N개
   ```

## Step 2: Blocked 처리 (최우선)

Status=블락드인 프로젝트 각각:
1. 페이지에서 blocked 사유 확인 (notion-fetch)
2. Slack Thread URL이 있으면:
   - slack_send_message로 스레드에 알림: "🚫 유저 확인 필요: {사유}"
   - slack_read_thread로 유저 응답 확인
   - 응답 있으면: 지시에 따라 상태 변경 + 재실행
3. Slack Thread URL이 없으면: 블락 사유만 출력

## Step 3: Stale 프로젝트 감지

Status=진행중인데 24시간 이상 업데이트 없는 프로젝트:
1. "⚠️ stale 프로젝트 감지: {name}" 출력
2. Slack Thread URL이 있으면 알림
3. --dry-run이 아니면: 블락드로 상태 변경 + 사유 "세션 타임아웃 — 재시작 필요"

## Step 4: Queued 실행 (최대 3개)

Status=진행예정인 프로젝트들 (최대 3개):
1. 각 프로젝트 상태를 진행중으로 변경 (notion-update-page)
2. 하나의 메시지에서 여러 Agent tool call로 병렬 디스패치:
   - 각 Agent: mode=bypassPermissions, subagent_type=general-purpose
   - prompts/manager.md + executor-base.md + 해당 skill executor 포함
   - Notion page_id와 원래 프롬프트 전달
3. 3개 초과 시: 나머지는 진행예정 유지

## Step 5: 결과 보고

--dry-run이면 계획만 출력 (실제 실행/상태 변경 없음). 아니면 실행 결과 요약.
