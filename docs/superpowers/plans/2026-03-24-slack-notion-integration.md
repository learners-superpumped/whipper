# Whipper Slack + Notion Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack에서 @whipper 태그로 일을 시키고, Notion todo 테이블로 전체 프로젝트를 관리하며, 주기적으로 자동 진행하는 시스템

**Architecture:** Slack polling daemon이 주기적으로 메시지를 확인 → 프로젝트 매칭/생성 → Claude Code 세션 디스패치. Notion DB가 전체 프로젝트의 single source of truth. 범용 cron hook으로 주기적 실행.

**Tech Stack:** Claude Code Plugin (hooks + commands), Slack MCP, Notion MCP, CronCreate API, jq, bash

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────┐
│                    Notion Todo DB                        │
│  ┌──────────┬────────┬──────────┬────────┬───────────┐  │
│  │ 진행예정  │ 진행중  │ 완료     │ 드랍   │ 블락드    │  │
│  └──────────┴────────┴──────────┴────────┴───────────┘  │
│         ↑ sync ↓                     ↑ status update     │
├─────────────────────────────────────────────────────────┤
│              whipper state layer                         │
│  .whipper/projects.json  ←→  Notion DB                  │
│  (thread_ts → project mapping)                           │
│  (project → session mapping)                             │
├─────────────────────────────────────────────────────────┤
│              Slack polling layer                          │
│  /whip-inbox  →  read mentions  →  match/create project  │
│               →  dispatch session  →  reply in thread     │
├─────────────────────────────────────────────────────────┤
│              Execution layer                              │
│  /whip-todo   →  scan todo DB  →  parallel sessions      │
│               →  blocked → Slack ask  →  update status    │
├─────────────────────────────────────────────────────────┤
│              Cron layer (generic)                         │
│  hooks/cron-hook.sh  →  CronCreate  →  periodic trigger  │
│  config/cron.json    →  skill + interval definitions      │
└─────────────────────────────────────────────────────────┘
```

## 상태 흐름

```
새 요청 (Slack/CLI) → 진행예정
                        ↓ whip-todo picks up
                      진행중
                        ↓ success / fail
                      완료 / 블락드 (유저 승인 필요)
                        ↓ 유저 응답 (Slack)
                      진행중 (재시도) / 드랍
```

---

## Task 1: 프로젝트 상태 레이어 (projects.json)

기존 `~/.claude/whipper-logs/index.json`은 실행 로그일 뿐. 프로젝트 전체 lifecycle을 관리할 새 상태 파일이 필요.

**Files:**
- Create: `scripts/core/projects.sh` — 프로젝트 CRUD 함수
- Create: `config/statuses.json` — 상태 정의
- Modify: `scripts/core/setup.sh` — 프로젝트 생성 시 projects.json에도 등록

### config/statuses.json

- [ ] **Step 1: 상태 정의 파일 생성**

```json
{
  "statuses": ["queued", "in_progress", "completed", "dropped", "blocked"],
  "display": {
    "queued": "진행예정",
    "in_progress": "진행중",
    "completed": "완료",
    "dropped": "드랍",
    "blocked": "블락드"
  },
  "transitions": {
    "queued": ["in_progress", "dropped"],
    "in_progress": ["completed", "blocked", "dropped"],
    "blocked": ["in_progress", "dropped"],
    "completed": [],
    "dropped": []
  }
}
```

### scripts/core/projects.sh

- [ ] **Step 2: 프로젝트 관리 함수 작성**

```bash
#!/bin/bash
# Project state management
set -euo pipefail
export LC_ALL=en_US.UTF-8

PROJECTS_FILE="$HOME/.claude/whipper-logs/projects.json"
mkdir -p "$(dirname "$PROJECTS_FILE")"
[[ ! -f "$PROJECTS_FILE" ]] && echo "[]" > "$PROJECTS_FILE"

# Create project entry
# Args: id prompt skill task_dir [slack_thread] [slack_channel] [notion_page_id]
create_project() {
  local id="$1" prompt="$2" skill="$3" task_dir="$4"
  local slack_thread="${5:-}" slack_channel="${6:-}" notion_page_id="${7:-}"
  local TEMP=$(mktemp)
  jq --arg id "$id" \
     --arg prompt "$prompt" \
     --arg skill "$skill" \
     --arg task_dir "$task_dir" \
     --arg status "queued" \
     --arg slack_thread "$slack_thread" \
     --arg slack_channel "$slack_channel" \
     --arg notion_page_id "$notion_page_id" \
     --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     '. += [{
       id: $id, prompt: $prompt, skill: $skill,
       task_dir: $task_dir, status: $status,
       slack_thread_ts: $slack_thread,
       slack_channel: $slack_channel,
       notion_page_id: $notion_page_id,
       session_id: "",
       created_at: $created, updated_at: $created,
       blocked_reason: "", blocked_at: null,
       last_reply_ts: ""
     }]' "$PROJECTS_FILE" > "$TEMP" && mv "$TEMP" "$PROJECTS_FILE"
}

# Update project status
update_project_status() {
  local id="$1" status="$2" reason="${3:-}"
  local TEMP=$(mktemp)
  jq --arg id "$id" \
     --arg status "$status" \
     --arg reason "$reason" \
     --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     'map(if .id == $id then
       .status = $status | .updated_at = $now |
       (if $status == "blocked" then .blocked_reason = $reason | .blocked_at = $now else . end)
     else . end)' "$PROJECTS_FILE" > "$TEMP" && mv "$TEMP" "$PROJECTS_FILE"
}

# Update project field (generic)
update_project_field() {
  local id="$1" field="$2" value="$3"
  local TEMP=$(mktemp)
  jq --arg id "$id" \
     --arg field "$field" \
     --arg value "$value" \
     --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     'map(if .id == $id then .[$field] = $value | .updated_at = $now else . end)' \
     "$PROJECTS_FILE" > "$TEMP" && mv "$TEMP" "$PROJECTS_FILE"
}

# Get projects by status
get_projects_by_status() {
  local status="$1"
  jq --arg s "$status" '[.[] | select(.status == $s)]' "$PROJECTS_FILE"
}

# Find project by slack thread
find_project_by_thread() {
  local channel="$1" thread_ts="$2"
  jq --arg ch "$channel" --arg ts "$thread_ts" \
     '[.[] | select(.slack_channel == $ch and .slack_thread_ts == $ts)] | first // empty' \
     "$PROJECTS_FILE"
}

# Get all projects summary
get_projects_summary() {
  jq 'group_by(.status) | map({status: .[0].status, count: length, items: [.[].id]})' "$PROJECTS_FILE"
}
```

- [ ] **Step 3: setup.sh에 프로젝트 등록 추가**

`scripts/core/setup.sh`의 global index 등록 후에 추가:

```bash
# Register in projects tracker
source "$PLUGIN_ROOT/scripts/core/projects.sh"
create_project "${DATE}-${SLUG}" "$PROMPT" "$SKILL" "$TASK_DIR"
```

- [ ] **Step 4: stop-hook.sh에 프로젝트 상태 업데이트 추가**

stop-hook.sh에서 status: passed일 때:
```bash
source "$PLUGIN_ROOT/scripts/core/projects.sh"
TASK_ID=$(basename "$TASK_DIR")
update_project_status "$TASK_ID" "completed"
```

status: failed이고 max_iterations 도달 시:
```bash
update_project_status "$TASK_ID" "blocked" "Max iterations reached — needs user review"
```

- [ ] **Step 5: 커밋**

```bash
git add config/statuses.json scripts/core/projects.sh scripts/core/setup.sh hooks/stop-hook.sh
git commit -m "feat: add project state management layer"
```

---

## Task 2: Notion Todo 테이블 연동

Notion DB를 프로젝트 상태의 external mirror로 사용. projects.json이 source of truth이고 Notion은 동기화 대상.

**Files:**
- Create: `config/notion.json` — Notion DB 설정
- Create: `commands/whip-notion-sync.md` — 수동 동기화 스킬
- Modify: `prompts/manager.md` — Notion 동기화 단계 추가

### Notion DB 스키마

- [ ] **Step 1: Notion DB 설정 파일 생성**

`config/notion.json`:
```json
{
  "todo_database_id": "",
  "properties": {
    "title": "Name",
    "status": "Status",
    "skill": "Skill",
    "prompt": "Prompt",
    "task_dir": "Task Dir",
    "created_at": "Created",
    "updated_at": "Updated",
    "blocked_reason": "Blocked Reason",
    "slack_thread": "Slack Thread"
  },
  "status_mapping": {
    "queued": "진행예정",
    "in_progress": "진행중",
    "completed": "완료",
    "dropped": "드랍",
    "blocked": "블락드"
  }
}
```

- [ ] **Step 2: Notion 동기화 스킬 작성**

`commands/whip-notion-sync.md`:
```markdown
---
description: "Sync whipper projects to Notion todo table"
argument-hint: "[--init|--push|--pull]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)
  - mcp__claude_ai_Notion__notion-search
  - mcp__claude_ai_Notion__notion-fetch
  - mcp__claude_ai_Notion__notion-create-database
  - mcp__claude_ai_Notion__notion-create-pages
  - mcp__claude_ai_Notion__notion-update-page
  - mcp__claude_ai_Notion__notion-query-database-view
---

# Notion Todo Sync

## 동작 모드

### --init (최초 1회)
1. Read config/notion.json
2. Notion에 "Whipper Todo" 데이터베이스가 없으면 생성:
   - notion-create-database 사용
   - Properties: Name (title), Status (select: 진행예정/진행중/완료/드랍/블락드),
     Skill (select), Prompt (rich_text), Task Dir (rich_text),
     Created (date), Updated (date), Blocked Reason (rich_text),
     Slack Thread (url)
3. 생성된 database_id를 config/notion.json의 todo_database_id에 저장

### --push (projects.json → Notion)
1. Read ~/.claude/whipper-logs/projects.json
2. Read config/notion.json for database_id
3. 각 프로젝트에 대해:
   - notion_page_id가 없으면: notion-create-pages로 새 페이지 생성, page_id를 projects.json에 저장
   - notion_page_id가 있으면: notion-update-page로 상태 동기화
4. 동기화 결과 출력

### --pull (Notion → projects.json)
1. notion-query-database-view로 전체 목록 조회
2. Notion에서 상태가 변경된 항목 확인 (유저가 Notion에서 직접 드랍이나 상태 변경한 경우)
3. projects.json 업데이트

### 인자 없이 실행 시
--push 모드로 동작 (기본)
```

- [ ] **Step 3: Manager에 Notion 동기화 훅 추가**

`prompts/manager.md`의 4단계 판정 후에 추가할 내용:

```markdown
## 5단계: Notion 동기화 (선택)
- config/notion.json에 todo_database_id가 설정되어 있으면:
  - 프로젝트 상태 변경 시 Notion 페이지도 업데이트
  - Notion MCP 도구 사용: notion-update-page
```

- [ ] **Step 4: setup.sh의 기존 --notion 플래그에 projects 연동 추가**

setup.sh의 기존 `--notion)` 케이스(19-20행)에 `NOTION_MODE=true`를 추가. 기존 `PROMPT_PARTS+=("--notion")` 유지.

setup.sh에서 `source projects.sh` + `create_project` 호출 이후에:
```bash
if [[ "${NOTION_MODE:-false}" == "true" ]]; then
  update_project_field "${DATE}-${SLUG}" "notion_sync" "true"
fi
```

**중요:** `source projects.sh`는 반드시 이 블록보다 먼저 실행되어야 함 (Task 1 Step 3에서 추가한 source 라인 활용).

- [ ] **Step 5: 커밋**

```bash
git add config/notion.json commands/whip-notion-sync.md prompts/manager.md scripts/core/setup.sh
git commit -m "feat: add Notion todo database sync"
```

---

## Task 3: Slack 연동 — 메시지 읽기 + 프로젝트 매칭

Slack MCP 도구로 @whipper 멘션을 폴링하고, thread_ts 기반으로 기존 프로젝트에 매칭하거나 새 프로젝트를 생성.

**Files:**
- Create: `commands/whip-inbox.md` — Slack 멘션 확인 + 처리 스킬
- Create: `config/slack.json` — Slack 설정 (채널, 봇 이름 등)
- Create: `scripts/slack/reply.sh` — Slack 메시지 포맷 유틸리티

### config/slack.json

- [ ] **Step 1: Slack 설정 파일 생성**

```json
{
  "bot_name": "whipper",
  "watch_channels": [],
  "default_channel": "",
  "last_checked_ts": "",
  "reply_in_thread": true
}
```

`watch_channels`가 비어있으면 모든 채널의 멘션을 확인.

- [ ] **Step 2: whip-inbox 스킬 작성**

`commands/whip-inbox.md`:
```markdown
---
description: "Check Slack for @whipper mentions and process them"
argument-hint: "[--once|--channel CHANNEL_ID]"
allowed-tools:
  - Agent
  - Read
  - Write
  - Edit
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)
  - mcp__claude_ai_Slack__slack_search_public_and_private
  - mcp__claude_ai_Slack__slack_read_channel
  - mcp__claude_ai_Slack__slack_read_thread
  - mcp__claude_ai_Slack__slack_send_message
  - mcp__claude_ai_Slack__slack_search_users
  - mcp__claude_ai_Notion__notion-update-page
  - mcp__claude_ai_Notion__notion-create-pages
  - mcp__claude_ai_Notion__notion-query-database-view
  - WebSearch
  - WebFetch
---

# Whip Inbox — Slack Message Processor

## 실행 흐름

### 1. 새 멘션 확인
1. Read config/slack.json에서 last_checked_ts 확인
2. slack_search_public_and_private로 "@whipper" 멘션 검색
   - last_checked_ts 이후 메시지만 필터
3. 새 멘션이 없으면 "📭 새 메시지 없음" 출력 후 종료

### 2. 각 멘션 처리 (순차)
각 멘션에 대해:

**a) 스레드 메시지인 경우 (thread_ts가 있음):**
1. source scripts/core/projects.sh
2. find_project_by_thread로 기존 프로젝트 검색
3. 프로젝트가 있으면:
   - 해당 프로젝트의 session_id로 기존 세션에 메시지 전달
   - 또는: 새 Agent 디스패치하되 이전 컨텍스트(task_dir) 포함
4. 프로젝트가 없으면:
   - 원본 스레드의 첫 메시지를 읽어서 컨텍스트 파악
   - 새 프로젝트 생성 (아래 b 절차)

**b) 새 메시지인 경우 (스레드가 아님):**
1. 메시지 내용에서 스킬 판단 (우선순위 순):
   - youtube.com/youtu.be URL 포함 → whip-learn
   - /research 또는 /조사 명시 → whip-research
   - /think 또는 /분석 명시 → whip-think
   - /medical 또는 /의료 명시 → whip-medical
   - 그 외 모든 경우 → whip (기본, Manager가 적절히 판단)
   - **스킬 판단이 불확실하면 whip(기본)으로 보낸다** — Manager가 내용을 보고 적절한 Executor를 선택
2. projects.sh의 create_project 호출 (slack_thread + slack_channel 포함)
3. Slack 스레드에 "🔥 프로젝트 생성됨: {id}" 응답
4. Agent 도구로 Executor 디스패치:
   - mode: bypassPermissions
   - Manager + Executor 프롬프트 전체 포함
   - 결과를 Slack 스레드에 회신하도록 지시
5. 결과 수신 후 Slack 스레드에 요약 회신

### 3. 스레드 자동 이어가기 (태그 없이)
**실행 제한:** 최대 5개 스레드만 점검 (가장 최근 updated_at 순). Agent 디스패치 타임아웃: 120초.
1. 진행중/블락드 프로젝트 중 slack_thread_ts가 있는 것만 필터 (최대 5개)
2. 각 스레드의 최신 메시지 확인 (slack_read_thread)
3. last_reply_ts 이후 봇이 아닌 유저의 새 메시지가 있으면:
   - 해당 프로젝트의 task_dir에서 최근 deliverables/ + iteration 로그 로드
   - Agent 디스패치: "이전 작업 컨텍스트 + 유저 새 지시" 포함 (timeout: 120s)
   - 결과를 스레드에 회신
   - update_project_field로 last_reply_ts 업데이트

### 4. 타임스탬프 업데이트
- config/slack.json의 last_checked_ts를 현재 시각으로 업데이트

### 5. 상태 동기화
- 처리한 프로젝트들의 상태를 Notion에도 반영 (notion_page_id가 있으면)
```

- [ ] **Step 3: Slack 응답 유틸리티 함수 추가**

`scripts/slack/reply.sh`:
```bash
#!/bin/bash
# Slack reply helper — called by Executor to reply in threads
# Usage: source reply.sh; slack_reply "channel" "thread_ts" "message"
# Note: actual Slack send is done via MCP tool in the Claude session,
# this script just formats the message

format_slack_reply() {
  local project_id="$1"
  local status="$2"
  local summary="$3"

  case "$status" in
    "started")  echo "🔥 작업 시작: $project_id" ;;
    "progress") echo "⏳ 진행중...\n$summary" ;;
    "completed") echo "✅ 완료!\n\n$summary" ;;
    "blocked")  echo "🚫 유저 확인 필요:\n$summary\n\n이 스레드에 답장으로 지시해주세요." ;;
    "failed")   echo "❌ 실패:\n$summary" ;;
  esac
}
```

- [ ] **Step 4: 커밋**

```bash
git add config/slack.json commands/whip-inbox.md scripts/slack/reply.sh
git commit -m "feat: add Slack inbox polling and thread-based project matching"
```

---

## Task 4: whip-todo 스킬 — Todo 리스트 점검 + 병렬 실행

현재 todo 리스트를 보고 진행예정 → 진행중으로 전환, 병렬 세션 실행, blocked 항목은 Slack으로 유저에게 확인.

**Files:**
- Create: `commands/whip-todo.md` — Todo 점검 스킬
- Create: `prompts/executor-todo.md` — Todo Executor 프롬프트

- [ ] **Step 1: whip-todo 스킬 작성**

`commands/whip-todo.md`:
```markdown
---
description: "Review todo list, run queued projects, check blocked items"
argument-hint: "[--dry-run]"
allowed-tools:
  - Agent
  - Read
  - Write
  - Edit
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)
  - mcp__claude_ai_Slack__slack_send_message
  - mcp__claude_ai_Slack__slack_read_thread
  - mcp__claude_ai_Notion__notion-update-page
  - mcp__claude_ai_Notion__notion-query-database-view
  - WebSearch
  - WebFetch
---

# Whip Todo — Project Queue Manager

## 실행 흐름

### 1. 현황 파악
1. source scripts/core/projects.sh
2. 모든 프로젝트 상태별 집계:
   ```
   📋 Whipper Todo 현황
   ────────────────────
   진행예정: N개
   진행중:   N개
   블락드:   N개
   완료:     N개
   드랍:     N개
   ```

### 2. Blocked 항목 처리 (최우선)
blocked 상태인 프로젝트 각각:
1. blocked_reason 확인
2. slack_thread_ts가 있으면:
   - Slack 스레드에 "🚫 이 작업이 블락되었습니다: {reason}\n진행/드랍/수정 중 선택해주세요" 전송
   - 스레드의 최신 유저 응답 확인
   - 응답이 있으면: 지시에 따라 상태 변경 (in_progress/dropped) + 재실행
3. slack_thread_ts가 없으면:
   - 블락 사유만 출력, 유저에게 직접 판단 요청

### 3. Queued 항목 실행 (병렬 Agent 디스패치)
queued 상태인 프로젝트들:
1. 각 프로젝트를 in_progress로 상태 변경
2. **하나의 메시지에 여러 Agent 도구 호출을 포함**하여 병렬 디스패치:
   - Claude Code는 단일 응답에서 여러 Agent tool call을 동시에 실행 가능
   - 각 Agent: mode: bypassPermissions, subagent_type: general-purpose
   - Manager + Executor 프롬프트 전체 포함
   - 해당 프로젝트의 prompt, skill, task_dir 전달
   - 최대 3개 동시 (한 메시지에 3개 Agent tool call)
3. 3개 초과 시: 나머지는 queued 상태 유지, 다음 사이클에서 처리
4. **주의:** 각 Agent는 독립적이므로 서로의 결과에 의존하면 안 됨

### 4. In-progress 항목 점검
진행중인 프로젝트들:
1. task_dir 존재 여부 확인
2. 최근 iteration 로그 확인
3. .claude/whipper.local.md 상태 확인
4. 세션이 살아있으면: skip (이미 실행중)
5. 세션이 죽었는데 status가 running이면: 재시작 (새 Agent 디스패치)

### 5. 결과 보고
1. 처리 결과 요약 출력
2. Notion 동기화 (config/notion.json에 database_id가 있으면)
3. --dry-run이면 실제 실행 없이 계획만 출력

### 6. Slack 결과 회신
실행된 프로젝트 중 slack_thread_ts가 있는 것들:
- 완료 시: "✅ 완료!" + 요약을 스레드에 전송
- 블락 시: "🚫 확인 필요" + 사유를 스레드에 전송
```

- [ ] **Step 2: executor-todo.md 작성**

`prompts/executor-todo.md`:
```markdown
# Todo Executor

너는 특정 프로젝트를 실행하는 Executor다.

## 받는 정보
- 프로젝트 ID, prompt, skill, task_dir
- 이전 iteration 피드백 (있으면)

## 실행 방법
1. 해당 skill의 executor 프롬프트를 따른다
2. 결과를 task_dir/deliverables/에 저장
3. Slack thread가 지정되어 있으면 결과 요약을 반환값에 포함

## 상태 업데이트
- 성공 시: projects.sh update_project_status "$ID" "completed"
- 블락 시: projects.sh update_project_status "$ID" "blocked" "사유"
- 유저 승인이 필요한 결정은 무조건 blocked 처리
```

- [ ] **Step 3: 커밋**

```bash
git add commands/whip-todo.md prompts/executor-todo.md
git commit -m "feat: add whip-todo skill for queue management and parallel execution"
```

---

## Task 5: 범용 Cron Hook — 주기적 스킬 실행

특정 스킬을 주기적으로 실행하는 범용 메커니즘. whipper 전용이 아니라 다른 플러그인에서도 재사용 가능한 구조.

**Files:**
- Create: `config/cron.json` — 크론 작업 정의
- Create: `scripts/core/cron-manager.sh` — 크론 등록/해제 관리
- Create: `commands/whip-cron.md` — 크론 관리 스킬
- Modify: `hooks/hooks.json` — SessionStart 훅 추가 (선택)

### 설계 원칙

크론 실행 방법은 2가지:

**A. Claude Code CronCreate API 활용 (권장)**
- Claude Code 내장 CronCreate 도구 사용
- OS cron이 아니라 Claude Code의 자체 스케줄러
- 장점: 플러그인 생태계 안에서 동작, 별도 인프라 불필요

**B. OS-level crontab + `claude` CLI (백업)**
- `claude --skill whip-todo --no-input` 같은 형태로 CLI 직접 호출
- crontab에 등록
- 장점: Claude Code 실행 여부와 무관하게 동작

둘 다 지원하되 A를 기본으로 사용.

- [ ] **Step 1: cron 설정 파일 생성**

`config/cron.json`:
```json
{
  "jobs": [
    {
      "id": "inbox-check",
      "skill": "whip-inbox",
      "schedule": "*/15 * * * *",
      "description": "Check Slack inbox every 15 minutes",
      "enabled": true,
      "args": "--once"
    },
    {
      "id": "todo-check",
      "skill": "whip-todo",
      "schedule": "0 */2 * * *",
      "description": "Review and process todo list every 2 hours",
      "enabled": true,
      "args": ""
    },
    {
      "id": "notion-sync",
      "skill": "whip-notion-sync",
      "schedule": "0 */1 * * *",
      "description": "Sync project states to Notion every hour",
      "enabled": true,
      "args": "--push"
    }
  ]
}
```

- [ ] **Step 2: cron-manager.sh 작성**

`scripts/core/cron-manager.sh`:
```bash
#!/bin/bash
# Generic cron manager for Claude Code plugins
# Usage: cron-manager.sh [register|unregister|list|status]
set -euo pipefail
export LC_ALL=en_US.UTF-8

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CRON_CONFIG="$PLUGIN_ROOT/config/cron.json"
CRON_STATE="$HOME/.claude/whipper-logs/cron-state.json"

mkdir -p "$(dirname "$CRON_STATE")"
[[ ! -f "$CRON_STATE" ]] && echo '{"registered_jobs": [], "last_run": {}}' > "$CRON_STATE"

list_jobs() {
  jq -r '.jobs[] | "\(.id)\t\(.enabled)\t\(.schedule)\t\(.description)"' "$CRON_CONFIG" | \
    column -t -s $'\t'
}

get_job() {
  local job_id="$1"
  jq --arg id "$job_id" '.jobs[] | select(.id == $id)' "$CRON_CONFIG"
}

# Record last run timestamp for a job
record_run() {
  local job_id="$1" result="$2"
  local TEMP=$(mktemp)
  jq --arg id "$job_id" \
     --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     --arg result "$result" \
     '.last_run[$id] = {timestamp: $ts, result: $result}' \
     "$CRON_STATE" > "$TEMP" && mv "$TEMP" "$CRON_STATE"
}

# Check if a job is due to run (based on last_run and schedule)
is_due() {
  local job_id="$1" schedule="$2"
  local last_run=$(jq -r --arg id "$job_id" '.last_run[$id].timestamp // "1970-01-01T00:00:00Z"' "$CRON_STATE")
  # Simple interval check — for full cron parsing, use python
  # This is a basic "has enough time passed?" check
  # Cross-platform epoch conversion (macOS + Linux)
  local last_epoch=$(python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${last_run}'.replace('Z','+00:00')).timestamp()))" 2>/dev/null || echo "0")
  local now_epoch=$(date "+%s")
  local diff=$((now_epoch - last_epoch))

  # Parse simple intervals from cron (*/N for minutes)
  local interval_minutes=$(echo "$schedule" | sed -n 's|^\*/\([0-9]*\) .*|\1|p')
  if [[ -n "$interval_minutes" ]]; then
    local interval_seconds=$((interval_minutes * 60))
    [[ $diff -ge $interval_seconds ]]
    return $?
  fi

  # For hourly (0 */N * * *)
  local interval_hours=$(echo "$schedule" | sed -n 's|^0 \*/\([0-9]*\) .*|\1|p')
  if [[ -n "$interval_hours" ]]; then
    local interval_seconds=$((interval_hours * 3600))
    [[ $diff -ge $interval_seconds ]]
    return $?
  fi

  # Default: run if more than 1 hour since last run
  [[ $diff -ge 3600 ]]
}

case "${1:-list}" in
  list) list_jobs ;;
  status) cat "$CRON_STATE" | jq '.' ;;
  due)
    # Output jobs that are due to run
    jq -c '.jobs[] | select(.enabled == true)' "$CRON_CONFIG" | while read -r job; do
      id=$(echo "$job" | jq -r '.id')
      schedule=$(echo "$job" | jq -r '.schedule')
      if is_due "$id" "$schedule"; then
        echo "$job"
      fi
    done
    ;;
  record)
    record_run "$2" "${3:-ok}"
    ;;
  *)
    echo "Usage: cron-manager.sh [list|status|due|record JOB_ID RESULT]"
    exit 1
    ;;
esac
```

- [ ] **Step 3: whip-cron 관리 스킬 작성**

`commands/whip-cron.md`:
```markdown
---
description: "Manage periodic task execution (cron jobs)"
argument-hint: "[--register|--unregister|--list|--run-due|--enable JOB|--disable JOB]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)
  - Agent
  - mcp__claude_ai_Slack__slack_send_message
  - mcp__claude_ai_Notion__notion-update-page
  - WebSearch
  - WebFetch
---

# Whip Cron — Periodic Task Manager

## 명령어

### --list
config/cron.json의 모든 작업 목록 + 마지막 실행 시각 표시

### --run-due
1. scripts/core/cron-manager.sh due로 실행할 작업 확인
2. 각 작업을 순차 실행:
   - 해당 skill의 명령어를 실행 (예: whip-inbox --once)
   - 실행 결과를 cron-manager.sh record로 기록
3. 실행 결과 요약 출력

### --register
CronCreate 도구를 사용하여 "whip-cron --run-due"를 시스템 크론에 등록.
기본 간격: 15분 (가장 짧은 작업 주기에 맞춤)

### --unregister
등록된 크론 작업 해제

### --enable / --disable JOB_ID
특정 작업 활성화/비활성화 (config/cron.json 수정)

## 범용 설계
이 크론 시스템은 config/cron.json의 포맷만 맞추면 어떤 스킬이든 주기적으로 실행 가능.
다른 플러그인에서 재사용하려면:
1. config/cron.json에 job 추가
2. scripts/core/cron-manager.sh를 복사하거나 심볼릭 링크
```

- [ ] **Step 4: SessionStart 훅으로 자동 점검 (선택)**

`hooks/hooks.json`에 SessionStart 훅 추가하여, 세션 시작 시 due 작업이 있으면 알림:

```json
{
  "hooks": {
    "Stop": [ ... ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/core/cron-manager.sh due",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

SessionStart 훅은 단순히 due 작업 목록만 출력. 실제 실행은 유저가 `/whip-cron --run-due`를 하거나 시스템 크론이 트리거.

- [ ] **Step 5: 커밋**

```bash
git add config/cron.json scripts/core/cron-manager.sh commands/whip-cron.md
git commit -m "feat: add generic cron system for periodic skill execution"
```

---

## Task 6: 통합 테스트 + allowed-tools 업데이트

기존 스킬들에 Notion/Slack MCP 도구 접근 권한 추가, 통합 테스트.

**Files:**
- Modify: `commands/whip.md` — allowed-tools에 Notion/Slack 추가
- Modify: `hooks/hooks.json` — SessionStart 훅 등록
- Create: `tests/test_projects.sh` — 프로젝트 관리 테스트
- Create: `tests/test_cron.sh` — 크론 매니저 테스트

- [ ] **Step 1: whip.md에 Slack/Notion 도구 추가**

기존 allowed-tools에 추가:
```yaml
allowed-tools:
  # ... 기존 도구들 ...
  - mcp__claude_ai_Slack__slack_send_message
  - mcp__claude_ai_Slack__slack_read_thread
  - mcp__claude_ai_Notion__notion-update-page
```

- [ ] **Step 2: 프로젝트 관리 테스트 작성**

`tests/test_projects.sh`:
```bash
#!/bin/bash
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

# Setup temp environment
export HOME=$(mktemp -d)
mkdir -p "$HOME/.claude/whipper-logs"

source "$PLUGIN_ROOT/scripts/core/projects.sh"

PASS=0; FAIL=0
check() {
  local name="$1"; shift
  if eval "$@" 2>/dev/null; then
    echo "✅ $name"; ((PASS++))
  else
    echo "❌ $name"; ((FAIL++))
  fi
}

# Test create
create_project "test-1" "Test prompt" "whip" "/tmp/test-1"
check "create_project" '[[ $(jq length "$PROJECTS_FILE") -eq 1 ]]'

# Test status update
update_project_status "test-1" "in_progress"
check "update_status" '[[ $(jq -r ".[0].status" "$PROJECTS_FILE") == "in_progress" ]]'

# Test blocked
update_project_status "test-1" "blocked" "Needs approval"
check "blocked_reason" '[[ $(jq -r ".[0].blocked_reason" "$PROJECTS_FILE") == "Needs approval" ]]'

# Test find by thread
create_project "test-2" "Slack test" "whip" "/tmp/test-2" "1234567890.123456"
update_project_field "test-2" "slack_channel" "C12345"
FOUND=$(find_project_by_thread "C12345" "1234567890.123456")
check "find_by_thread" '[[ -n "$FOUND" ]]'

# Test get by status
BLOCKED=$(get_projects_by_status "blocked")
check "get_by_status" '[[ $(echo "$BLOCKED" | jq length) -eq 1 ]]'

# Test summary
SUMMARY=$(get_projects_summary)
check "summary" '[[ $(echo "$SUMMARY" | jq length) -gt 0 ]]'

# Cleanup
rm -rf "$HOME"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
```

- [ ] **Step 3: 크론 매니저 테스트 작성**

`tests/test_cron.sh`:
```bash
#!/bin/bash
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"
export HOME=$(mktemp -d)
mkdir -p "$HOME/.claude/whipper-logs"

PASS=0; FAIL=0
check() {
  local name="$1"; shift
  if eval "$@" 2>/dev/null; then
    echo "✅ $name"; ((PASS++))
  else
    echo "❌ $name"; ((FAIL++))
  fi
}

# Test list
OUTPUT=$(bash "$PLUGIN_ROOT/scripts/core/cron-manager.sh" list)
check "list_jobs" '[[ -n "$OUTPUT" ]]'

# Test record
bash "$PLUGIN_ROOT/scripts/core/cron-manager.sh" record "inbox-check" "ok"
check "record_run" '[[ $(jq -r ".last_run[\"inbox-check\"].result" "$HOME/.claude/whipper-logs/cron-state.json") == "ok" ]]'

# Test due (should be due since we just started)
DUE=$(bash "$PLUGIN_ROOT/scripts/core/cron-manager.sh" due)
check "due_check" 'true'  # At minimum, should not error

rm -rf "$HOME"
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
```

- [ ] **Step 4: hooks.json 업데이트**

```json
{
  "description": "Whipper hooks for loop control and cron",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop-hook.sh"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/core/cron-manager.sh due 2>/dev/null | head -3",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: 테스트 실행 확인**

```bash
bash tests/test_projects.sh
bash tests/test_cron.sh
```

- [ ] **Step 6: 커밋**

```bash
git add tests/test_projects.sh tests/test_cron.sh hooks/hooks.json
git commit -m "feat: integration tests and hook updates for Slack/Notion"
```

---

## Task 7: 문서 업데이트 + plugin.json 업데이트

**Files:**
- Modify: `.claude-plugin/plugin.json` — description 업데이트
- Modify: `config/api-keys.json` — Slack/Notion은 MCP 기반이라 키 불필요, 설명만 추가

- [ ] **Step 1: plugin.json 업데이트**

```json
{
  "name": "whipper",
  "description": "Manager-Executor loop with Slack inbox, Notion todo sync, and periodic cron execution. Defines success criteria, executes via subagents, evaluates ruthlessly, iterates until passed.",
  "author": {
    "name": "whipper"
  }
}
```

- [ ] **Step 2: 커밋 + 푸시**

```bash
git add -A
git commit -m "docs: update plugin description for Slack/Notion integration"
git push origin main
```

---

## 구현 순서 요약

| 순서 | Task | 의존성 | 핵심 산출물 |
|------|------|--------|------------|
| 1 | 프로젝트 상태 레이어 | 없음 | projects.sh, statuses.json |
| 2 | Notion 동기화 | Task 1 | whip-notion-sync.md, notion.json |
| 3 | Slack inbox + 스레드 연속성 | Task 1 | whip-inbox.md, slack.json, reply.sh |
| 4 | whip-todo | Task 1, 3 | whip-todo.md, executor-todo.md |
| 5 | 범용 Cron | Task 3, 4 | whip-cron.md, cron-manager.sh |
| 6 | 통합 테스트 | Task 1-5 | test_projects.sh, test_cron.sh |
| 7 | 문서 + 배포 | Task 6 | plugin.json 업데이트 |

## 제약 사항 및 참고

1. **Slack MCP는 Claude AI 제공** — 별도 봇 서버 불필요. `mcp__claude_ai_Slack__*` 도구가 이미 사용 가능
2. **Notion MCP도 동일** — `mcp__claude_ai_Notion__*` 도구 사용. API 키 대신 OAuth 인증
3. **세션 스폰 제약** — Claude Code CLI로 새 세션을 프로그래매틱하게 시작하는 건 Agent 도구(서브에이전트)로 해결. 독립 프로세스가 아니라 현재 세션 안에서 병렬 Agent 디스패치
4. **크론 실행** — CronCreate 도구 또는 OS crontab + `claude` CLI. 두 방법 모두 지원
5. **projects.json이 source of truth** — Notion은 mirror. 충돌 시 projects.json 우선
