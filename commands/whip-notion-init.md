---
description: "Initialize Notion database and verify Slack setup"
argument-hint: ""
allowed-tools: [
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test *:*)",
  "mcp__claude_ai_Notion__notion-create-database",
  "mcp__claude_ai_Notion__notion-search",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-get-teams"
]
---

# Whip Notion Init — 초기 설정

## Step 1: Notion DB 확인/생성

1. notion-search로 "Whipper Projects" 데이터베이스가 이미 있는지 확인
2. **있으면**: database_id를 config/notion.json에 저장
3. **없으면**: notion-create-database로 생성:
   - Name: "Whipper Projects"
   - Schema (SQL DDL):
     ```sql
     CREATE TABLE "Whipper Projects" (
       "Name" TITLE,
       "Status" SELECT('진행예정', '진행중', '완료', '드랍', '블락드'),
       "Skill" SELECT('whip', 'whip-learn', 'whip-research', 'whip-think', 'whip-medical'),
       "Slack Thread" URL,
       "Iteration" NUMBER,
       "Created" CREATED_TIME
     );
     ```
   - 생성된 database_id를 config/notion.json의 database_id 필드에 저장

## Step 2: 환경 확인

1. WHIPPER_NOTION_TOKEN 또는 NOTION_TOKEN 환경변수 확인
   - 없으면 안내: https://www.notion.so/my-integrations 에서 생성
2. config/slack.json 존재 + 토큰 확인
   - 없으면 안내:
     - https://api.slack.com/apps 에서 새 앱 생성
     - Socket Mode 활성화 → App-Level Token (xapp-...)
     - Bot Token Scopes: app_mentions:read, chat:write, channels:history, channels:read
     - Event Subscriptions: app_mention, message.channels
     - Install to Workspace → Bot User OAuth Token (xoxb-...)

## Step 3: 결과 요약

설정 상태를 출력:
```
Whipper 설정 현황
─────────────────
Notion DB:     ✅/❌ (database_id: ...)
Notion Token:  ✅/❌
Slack config:  ✅/❌
```
