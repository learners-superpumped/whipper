# Whipper Slack + Notion Integration v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack 실시간 봇 + Notion을 유일한 저장소로 사용하여, 로컬 파일 의존을 `.claude/whipper.local.md` 하나로 줄인다.

**Architecture:** Slack Bolt(Socket Mode) 데몬이 멘션/스레드를 실시간 수신 → Notion DB에 프로젝트 생성 → `claude` CLI spawn → Manager/Executor가 Notion에 직접 기록. stop-hook은 `fetch_iteration.py`로 Notion에서 읽기.

**Tech Stack:** Python (Slack Bolt, slack_sdk, APScheduler), Notion MCP tools, catbox.moe (이미지 호스팅), launchd (데몬 관리), Claude Code CLI

---

## File Structure

### 신규 생성 파일

```
scripts/
  notion/
    publisher.py          — Notion 페이지 CRUD (범용, upload_images.py 패턴 일반화)
    fetch_iteration.py    — stop-hook용: Notion에서 iteration 로그 읽기 (10줄)
  daemon/
    slack_bot.py          — Slack Bolt + Socket Mode 메인 데몬
    scheduler.py          — APScheduler 기반 주기 작업 (todo 점검)
    requirements.txt      — slack-bolt, slack-sdk, apscheduler
    com.whipper.daemon.plist  — macOS launchd 자동 시작 설정
config/
  notion.json             — Notion DB ID, 상태 매핑
  slack.json              — Slack Bot Token, App Token
commands/
  whip-todo.md            — Notion DB 큐 관리 + 병렬 실행 스킬
  whip-notion-init.md     — 최초 설정: Notion DB 생성 + Slack App 확인
prompts/
  executor-todo.md        — whip-todo용 Executor 프롬프트
tests/
  test_notion_publisher.py — publisher.py 단위 테스트
  test_slack_bot.py        — 데몬 이벤트 핸들링 테스트
```

### 수정 파일

```
prompts/manager.md:5-15       — 0단계: .whipper/tasks/ → Notion DB 쿼리
prompts/manager.md:44         — README.md 기록 → Notion 페이지 본문
prompts/manager.md:78-83      — iteration 로그 → Notion 페이지 코멘트
prompts/executor-base.md:49-51 — 산출물 저장 → Notion 페이지
hooks/stop-hook.sh (전체)      — TASK_DIR→TASK_ID, Notion fetch, 완전 재작성
scripts/core/setup.sh (전체)   — 폴더 생성 제거, TASK_DIR→TASK_ID, notion_page_id 추가
scripts/core/logger.sh:8-20   — update_global_index가 task_id 받도록 수정
commands/whip.md:4-17          — allowed-tools에 Notion MCP 추가
commands/whip-learn.md:4-18    — 동일
commands/whip-research.md      — 동일
commands/whip-think.md         — 동일
commands/whip-medical.md       — 동일
.claude-plugin/plugin.json     — description 업데이트
```

---

## Task 1: Notion 퍼블리셔 + config

upload_images.py의 catbox.moe 패턴을 일반화하고, Notion 페이지 CRUD를 담당하는 publisher.py 작성.

**Files:**
- Create: `scripts/notion/publisher.py`
- Create: `config/notion.json`
- Create: `scripts/notion/fetch_iteration.py`
- Test: `tests/test_notion_publisher.py`

- [ ] **Step 1: config/notion.json 생성**

```json
{
  "database_id": "",
  "status_mapping": {
    "queued": "진행예정",
    "in_progress": "진행중",
    "completed": "완료",
    "dropped": "드랍",
    "blocked": "블락드"
  },
  "properties": {
    "title": "Name",
    "status": "Status",
    "skill": "Skill",
    "slack_thread_url": "Slack Thread",
    "created_at": "Created",
    "iteration": "Iteration"
  }
}
```

- [ ] **Step 2: publisher.py 작성**

```python
#!/usr/bin/env python3
"""Notion publisher — 프로젝트 페이지 CRUD + 콘텐츠 작성.

Notion MCP 도구를 직접 호출하지 않음 (Claude 세션 안에서만 가능).
대신 이 모듈은:
1. Notion에 올릴 콘텐츠를 구조화된 JSON으로 변환
2. Claude 세션이 MCP 도구로 올릴 수 있도록 지시문 생성
3. catbox.moe 이미지 업로드 (upload_images.py 패턴 재사용)
"""
import json
import sys
import os
import requests
from pathlib import Path

CATBOX_URL = "https://catbox.moe/user/api.php"

def upload_to_catbox(file_path: str) -> str:
    """파일을 catbox.moe에 업로드하고 URL 반환."""
    with open(file_path, "rb") as f:
        resp = requests.post(CATBOX_URL, data={"reqtype": "fileupload"}, files={"fileToUpload": f})
    resp.raise_for_status()
    return resp.text.strip()

def upload_directory(directory: str) -> dict:
    """디렉토리 내 이미지/파일을 catbox.moe에 업로드. {filename: url} 반환."""
    results = {}
    if not os.path.isdir(directory):
        return results
    for f in sorted(os.listdir(directory)):
        fpath = os.path.join(directory, f)
        if os.path.isfile(fpath) and f.lower().endswith((".jpg", ".png", ".gif", ".pdf", ".webp")):
            try:
                url = upload_to_catbox(fpath)
                results[f] = url
            except Exception as e:
                print(f"Warning: Failed to upload {f}: {e}", file=sys.stderr)
    return results

def format_success_criteria(criteria_text: str) -> str:
    """성공기준 텍스트를 Notion 블록용 마크다운으로 변환."""
    return f"## 성공기준\n\n{criteria_text}"

def format_iteration_log(iteration: int, executor_log: str, manager_eval: str) -> str:
    """Iteration 로그를 Notion 토글 블록용 마크다운으로 변환."""
    return f"""## ▶ Iteration {iteration}

### Executor 로그
{executor_log}

### Manager 평가
{manager_eval}
"""

def format_deliverable(title: str, content: str, media_urls: dict = None) -> str:
    """최종 산출물을 Notion 페이지 본문용 마크다운으로 변환."""
    result = f"## 결과물: {title}\n\n{content}"
    if media_urls:
        result += "\n\n### 첨부 파일\n"
        for name, url in media_urls.items():
            if url.endswith((".jpg", ".png", ".webp", ".gif")):
                result += f"\n![{name}]({url})\n"
            else:
                result += f"\n- [{name}]({url})\n"
    return result

if __name__ == "__main__":
    # CLI: upload directory
    if len(sys.argv) >= 2:
        directory = sys.argv[1]
        urls = upload_directory(directory)
        print(json.dumps(urls, indent=2, ensure_ascii=False))
```

- [ ] **Step 3: fetch_iteration.py 작성**

이 스크립트는 stop-hook.sh에서 호출됨. Notion API를 직접 호출하여 iteration 로그를 가져옴.
**주의:** Notion MCP 도구는 Claude 세션 안에서만 사용 가능. 이 스크립트는 Notion Internal Integration Token을 사용하여 REST API를 직접 호출.

**주의: stdlib만 사용 (requests 금지). stop-hook에서 호출되므로 pip 의존성 없이 동작해야 함.**

```python
#!/usr/bin/env python3
"""stop-hook용: Notion 페이지의 코멘트에서 iteration 로그를 읽어 stdout에 출력.

Usage: python3 fetch_iteration.py <notion_page_id> <iteration_number>
Env: WHIPPER_NOTION_TOKEN 또는 NOTION_TOKEN

stdlib만 사용 (requests 없음) — stop-hook 안정성 보장.
iteration 로그는 Notion 코멘트로 저장됨 (notion-create-comment).
"""
import sys
import os
import json
import urllib.request
import urllib.error

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def get_token():
    token = os.environ.get("WHIPPER_NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    if not token:
        # 토큰 없으면 빈 결과 (stop-hook이 빈 피드백으로 처리)
        print(json.dumps({"executor_log": "", "manager_eval": ""}))
        sys.exit(0)
    return token

def api_get(path: str, token: str) -> dict:
    """Notion API GET 요청 (urllib만 사용)."""
    req = urllib.request.Request(
        f"{NOTION_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError:
        return {"results": []}

def get_comments(page_id: str, token: str) -> list:
    """페이지의 코멘트를 가져온다."""
    data = api_get(f"/comments?block_id={page_id}&page_size=100", token)
    return data.get("results", [])

def extract_comment_text(comment: dict) -> str:
    """코멘트에서 plain text를 추출."""
    rich_texts = comment.get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich_texts)

def find_iteration_content(comments: list, iteration: int) -> tuple:
    """코멘트에서 iteration N의 executor log와 manager eval을 찾는다.

    Manager가 코멘트를 이 형식으로 작성:
    [Iteration N - Executor Log] ...내용...
    [Iteration N - Manager Eval] ...내용...
    """
    executor_log = ""
    manager_eval = ""
    exec_prefix = f"[Iteration {iteration} - Executor Log]"
    eval_prefix = f"[Iteration {iteration} - Manager Eval]"

    for comment in comments:
        text = extract_comment_text(comment)
        if text.startswith(exec_prefix):
            executor_log = text[len(exec_prefix):].strip()
        elif text.startswith(eval_prefix):
            manager_eval = text[len(eval_prefix):].strip()

    return executor_log, manager_eval

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"executor_log": "", "manager_eval": ""}))
        sys.exit(0)

    page_id = sys.argv[1]
    iteration = int(sys.argv[2])
    token = get_token()
    comments = get_comments(page_id, token)
    executor_log, manager_eval = find_iteration_content(comments, iteration)

    print(json.dumps({"executor_log": executor_log, "manager_eval": manager_eval}, ensure_ascii=False))
```

- [ ] **Step 4: 테스트 작성**

```python
#!/usr/bin/env python3
"""tests/test_notion_publisher.py"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "notion"))
from publisher import format_success_criteria, format_iteration_log, format_deliverable, upload_directory

def test_format_success_criteria():
    result = format_success_criteria("1. 리조트 3곳 이상\n2. 반려견 동반 가능")
    assert "## 성공기준" in result
    assert "리조트 3곳" in result

def test_format_iteration_log():
    result = format_iteration_log(1, "검색 수행함", "PASS")
    assert "Iteration 1" in result
    assert "검색 수행함" in result
    assert "PASS" in result

def test_format_deliverable_with_media():
    urls = {"photo.jpg": "https://files.catbox.moe/abc.jpg"}
    result = format_deliverable("보고서", "내용입니다", urls)
    assert "![photo.jpg]" in result
    assert "catbox.moe" in result

def test_format_deliverable_without_media():
    result = format_deliverable("보고서", "내용입니다")
    assert "보고서" in result
    assert "첨부" not in result

def test_upload_directory_empty():
    with tempfile.TemporaryDirectory() as d:
        assert upload_directory(d) == {}

def test_upload_directory_nonexistent():
    assert upload_directory("/nonexistent/path") == {}

if __name__ == "__main__":
    tests = [f for f in dir() if f.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            globals()[t]()
            print(f"✅ {t}")
            passed += 1
        except Exception as e:
            print(f"❌ {t}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 5: 테스트 실행**

Run: `cd /Users/nevermind/.claude/plugins/marketplaces/whipper && python3 tests/test_notion_publisher.py`
Expected: 6 passed, 0 failed

- [ ] **Step 6: 커밋**

```bash
git add scripts/notion/publisher.py scripts/notion/fetch_iteration.py config/notion.json tests/test_notion_publisher.py
git commit -m "feat: add Notion publisher and fetch_iteration for stop-hook"
```

---

## Task 2: stop-hook + setup.sh Notion 연동

stop-hook이 로컬 파일 대신 Notion에서 읽고, setup.sh가 notion_page_id를 state file에 포함하도록 수정.

**Files:**
- Modify: `hooks/stop-hook.sh:39-42,67-78`
- Modify: `scripts/core/setup.sh:47-67`
- Modify: `config/api-keys.json` (Notion 토큰 추가)

- [ ] **Step 1: config/api-keys.json에 Notion 토큰 추가**

```json
{
  "openai": { ... },
  "gemini": { ... },
  "notion": {
    "env_var": "WHIPPER_NOTION_TOKEN",
    "fallback": "NOTION_TOKEN",
    "required_by": ["whip", "whip-learn", "whip-research", "whip-think", "whip-medical", "whip-todo"],
    "description": "Notion Internal Integration Token"
  }
}
```

- [ ] **Step 2: setup.sh 수정 — 완전 diff**

`scripts/core/setup.sh`에서 변경할 모든 부분:

**a) 47행 부근 — TASK_DIR → TASK_ID, 폴더 생성 제거:**
```bash
# 기존:
# TASK_DIR=".whipper/tasks/${DATE}-${SLUG}"
# mkdir -p "$TASK_DIR/iterations" "$TASK_DIR/deliverables" "$TASK_DIR/resources"

# 신규:
TASK_ID="${DATE}-${SLUG}"
```

**b) state file — task_dir → task_id, notion_page_id 추가:**
```bash
cat > .claude/whipper.local.md <<EOF
---
active: true
skill: $SKILL
iteration: 1
max_iterations: $MAX_ITERATIONS
session_id: ${CLAUDE_CODE_SESSION_ID:-}
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
task_id: "$TASK_ID"
notion_page_id: ""
status: running
---

$PROMPT
EOF
```

**c) global index — $TASK_DIR 참조를 $TASK_ID로:**
```bash
jq --arg id "${DATE}-${SLUG}" \
   --arg cmd "$PROMPT" \
   --arg skill "$SKILL" \
   --arg project "$PWD" \
   --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '. += [{id: $id, command: $cmd, skill: $skill, project: $project, started_at: $started, finished_at: null, iterations: 0, result: "running"}]' \
   "$GLOBAL_INDEX" > "$TEMP" && mv "$TEMP" "$GLOBAL_INDEX"
```
(path 필드 삭제 — 로컬 경로가 더 이상 존재하지 않으므로)

**d) 출력 — TASK_DIR 참조 제거:**
```bash
cat <<EOF
🔥 Whipper activated!

Skill: $SKILL
Task ID: $TASK_ID
Iteration: 1
Max iterations: $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo "unlimited"; fi)

$PROMPT
EOF
```

- [ ] **Step 2b: logger.sh 수정**

`scripts/core/logger.sh`의 `update_global_index` 함수에서 `task_id`로 통일:
```bash
update_global_index() {
  local task_id="$1" result="$2" iterations="$3"
  # ... jq에서 .id == $task_id로 매칭 (기존과 동일, 변수명만 명확화)
}
```
(실제 로직은 이미 id 기반 매칭이므로 큰 변경 없음)

- [ ] **Step 3: stop-hook.sh 수정 — 전체 TASK_DIR→TASK_ID + Notion 읽기**

stop-hook.sh의 변경이 필요한 모든 부분:

**a) FRONTMATTER 파싱 (18행 부근) — task_dir → task_id + notion_page_id 추가:**
```bash
TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/')
NOTION_PAGE_ID=$(echo "$FRONTMATTER" | grep '^notion_page_id:' | sed 's/notion_page_id: *//' | sed 's/^"\(.*\)"$/\1/')
```
(`TASK_DIR` 파싱 라인 삭제)

**b) passed 처리 (39-42행) — TASK_ID로 변경:**
```bash
if [[ "$STATUS" == "passed" ]]; then
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  source "$PLUGIN_ROOT/scripts/core/logger.sh"
  update_global_index "$TASK_ID" "passed" "$ITERATION"
  rm "$STATE_FILE"
  exit 0
fi
```

**c) max_iterations 처리 (49-51행) — 동일:**
```bash
  update_global_index "$TASK_ID" "max_iterations" "$ITERATION"
```

**d) iteration 로그 읽기 (67-78행) — Notion에서 읽기:**
```bash
# Notion에서 iteration 로그 읽기 (stdlib만 사용하는 fetch_iteration.py)
FEEDBACK=""
EXEC_LOG=""
if [[ -n "$NOTION_PAGE_ID" ]]; then
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  NOTION_DATA=$(python3 "$PLUGIN_ROOT/scripts/notion/fetch_iteration.py" "$NOTION_PAGE_ID" "$ITERATION" 2>/dev/null || echo '{}')
  FEEDBACK=$(echo "$NOTION_DATA" | jq -r '.manager_eval // ""')
  EXEC_LOG=$(echo "$NOTION_DATA" | jq -r '.executor_log // ""')
fi
```

**Notion 미설정 시 (하위 호환):** `NOTION_PAGE_ID`가 비어있으면 FEEDBACK과 EXEC_LOG가 빈 문자열 → stop-hook은 원래 프롬프트만으로 재주입 (피드백 없이).

- [ ] **Step 4: 커밋**

```bash
git add hooks/stop-hook.sh scripts/core/setup.sh config/api-keys.json
git commit -m "feat: stop-hook reads from Notion, setup.sh adds notion_page_id"
```

---

## Task 3: Manager/Executor 프롬프트 Notion 연동

Manager와 Executor가 로컬 파일 대신 Notion에 기록하도록 프롬프트 수정.

**Files:**
- Modify: `prompts/manager.md:5-15,44,78-83`
- Modify: `prompts/executor-base.md:49-51`
- Modify: `commands/whip.md:4-17` (allowed-tools에 Notion MCP 추가)
- Modify: 나머지 commands/*.md (동일)

- [ ] **Step 1: manager.md 수정**

**0단계** (5-15행) 변경 — `.whipper/tasks/` 스캔을 Notion DB 쿼리로:

```markdown
## 0단계: 선행 작업 확인

명령을 처리하기 전에, 현재 명령이 이전 작업의 후속/연장인지 확인한다.

1. config/notion.json에서 database_id를 읽는다
2. database_id가 있으면: Notion DB에서 **당일 프로젝트**들을 쿼리한다 (notion-query-database-view)
3. 현재 명령이 이전 작업과 관련 있는지 판단한다
4. **관련 있으면**:
   - 이전 프로젝트의 Notion 페이지를 읽어서 컨텍스트를 파악한다 (notion-fetch)
   - 새 프로젝트 페이지에 `선행 작업` 링크를 추가한다
   - Executor에게 이전 결과물을 컨텍스트로 함께 전달한다
5. **관련 없으면**: 새 작업으로 진행
6. database_id가 없으면: 선행 작업 확인을 건너뛴다 (Notion 미설정 상태)
```

**2단계 끝** (44행) 변경 — README.md 대신 Notion 페이지:

```markdown
### Notion 프로젝트 페이지 생성

1. config/notion.json에서 database_id를 읽는다
2. database_id가 있으면:
   - notion-create-pages로 프로젝트 페이지 생성 (DB 하위)
   - Properties: Name=명령요약, Status=진행중, Skill=현재스킬, Created=now
   - 본문에 매핑표와 성공기준 작성
   - 생성된 page_id를 .claude/whipper.local.md의 notion_page_id에 sed로 기록
3. database_id가 없으면: 콘솔에 성공기준을 출력 (기존 동작 호환)
```

**4단계** (78-83행) 변경 — iteration 로그를 Notion 코멘트로:

**왜 코멘트인가:** `notion-update-page` MCP 도구는 페이지 properties만 업데이트 가능하고 본문 블록 추가는 불가. `notion-create-comment`로 코멘트를 달면 (1) 본문을 건드리지 않고 (2) fetch_iteration.py가 Comments API로 쉽게 읽을 수 있음.

```markdown
### 평가 기록

notion_page_id가 있으면:
- Executor 로그를 코멘트로 추가 (notion-create-comment):
  "[Iteration {N} - Executor Log] {로그 내용}"
- Manager 평가를 코멘트로 추가 (notion-create-comment):
  "[Iteration {N} - Manager Eval] {평가표}"
- 프로젝트 페이지의 Iteration 속성을 현재 N으로 업데이트 (notion-update-page)

notion_page_id가 없으면:
- 콘솔에 평가 결과 출력 (기존 동작 호환)
```

- [ ] **Step 2: executor-base.md 수정**

49-51행 (산출물 저장) 변경:

```markdown
## 산출물 저장

- 이미지/스크린샷/GIF → catbox.moe에 업로드 (python3 scripts/notion/publisher.py 사용)
- 텍스트 산출물 → Manager에게 반환 (Manager가 Notion에 기록)
- 대용량 파일 → catbox.moe 업로드 후 URL을 결과에 포함
```

- [ ] **Step 3: commands/*.md에 Notion MCP 도구 추가**

`commands/whip.md`의 allowed-tools에 추가:

```yaml
allowed-tools: [
  "Agent",
  "Read", "Write", "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test *:*)", "Bash(sed *:*)", "Bash(cat *:*)", "Bash(mkdir *:*)", "Bash(chmod *:*)",
  "WebSearch", "WebFetch",
  "mcp__claude_ai_Notion__notion-create-pages",
  "mcp__claude_ai_Notion__notion-update-page",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-create-comment",
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-search"
]
```
(python3 경로를 CLAUDE_PLUGIN_ROOT/scripts로 제한, notion-create-comment 추가)

whip-learn.md, whip-research.md, whip-think.md, whip-medical.md에도 동일하게 추가.

- [ ] **Step 4: 커밋**

```bash
git add prompts/manager.md prompts/executor-base.md commands/whip.md commands/whip-learn.md commands/whip-research.md commands/whip-think.md commands/whip-medical.md
git commit -m "feat: Manager/Executor write to Notion instead of local files"
```

---

## Task 4: whip-notion-init 스킬

최초 1회 실행: Notion DB 생성 + Slack App 토큰 확인.

**Files:**
- Create: `commands/whip-notion-init.md`

- [ ] **Step 1: whip-notion-init.md 작성**

```markdown
---
description: "Initialize Notion database and verify Slack app setup"
argument-hint: ""
allowed-tools: [
  "Read", "Write", "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
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

## Step 2: Notion Token 확인

1. WHIPPER_NOTION_TOKEN 또는 NOTION_TOKEN 환경변수가 설정되어 있는지 확인
2. 없으면: 안내 메시지 출력
   - https://www.notion.so/my-integrations 에서 Internal Integration 생성
   - 토큰을 환경변수로 설정: `export WHIPPER_NOTION_TOKEN=ntn_...`
   - 위에서 생성한 DB 페이지에서 Integration을 Connect

## Step 3: Slack App 확인

1. config/slack.json 읽기
2. bot_token과 app_token이 비어있으면: 안내 메시지 출력
   - https://api.slack.com/apps 에서 새 앱 생성
   - Socket Mode 활성화 → App-Level Token 생성 (xapp-...)
   - Bot Token Scopes: app_mentions:read, chat:write, channels:history, channels:read
   - Event Subscriptions: app_mention, message.channels
   - Install to Workspace → Bot User OAuth Token (xoxb-...)
   - config/slack.json에 토큰 저장

## Step 4: 결과 출력

설정 상태 요약 출력:
- Notion DB: ✅/❌ (database_id)
- Notion Token: ✅/❌
- Slack Bot Token: ✅/❌
- Slack App Token: ✅/❌
```

- [ ] **Step 2: config/slack.json 생성**

```json
{
  "bot_token": "",
  "app_token": "",
  "bot_user_id": ""
}
```

- [ ] **Step 3: 커밋**

```bash
git add commands/whip-notion-init.md config/slack.json
git commit -m "feat: add whip-notion-init skill for initial setup"
```

---

## Task 5: Slack 데몬

Slack Bolt + Socket Mode로 실시간 이벤트 수신 → `claude` CLI spawn.

**Files:**
- Create: `scripts/daemon/slack_bot.py`
- Create: `scripts/daemon/scheduler.py`
- Create: `scripts/daemon/requirements.txt`
- Create: `scripts/daemon/com.whipper.daemon.plist`
- Test: `tests/test_slack_bot.py`

- [ ] **Step 1: requirements.txt 생성**

```
slack-bolt>=1.18.0
slack-sdk>=3.27.0
apscheduler>=3.10.0
requests>=2.31.0
```

- [ ] **Step 2: slack_bot.py 작성**

```python
#!/usr/bin/env python3
"""Whipper Slack Bot — Socket Mode 데몬.

@whipper 멘션 수신 → Notion 프로젝트 생성 → claude CLI spawn → 결과 회신.
스레드 답장 → 기존 프로젝트 컨텍스트 로드 → 이어서 처리.
"""
import os
import sys
import json
import subprocess
import threading
import logging
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("whipper-daemon")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PLUGIN_ROOT / "config"

def load_config():
    slack_cfg = json.loads((CONFIG_DIR / "slack.json").read_text())
    notion_cfg = json.loads((CONFIG_DIR / "notion.json").read_text())
    return slack_cfg, notion_cfg

def _find_latest_notion_page(database_id: str) -> str:
    """Notion DB에서 가장 최근 생성된 프로젝트의 page_id를 반환.
    stdlib만 사용 (fetch_iteration.py와 동일 패턴)."""
    if not database_id:
        return ""
    token = os.environ.get("WHIPPER_NOTION_TOKEN") or os.environ.get("NOTION_TOKEN")
    if not token:
        return ""
    try:
        import urllib.request
        data = json.dumps({
            "sorts": [{"property": "Created", "direction": "descending"}],
            "page_size": 1
        }).encode()
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            results = result.get("results", [])
            return results[0]["id"] if results else ""
    except Exception:
        return ""

def create_app():
    slack_cfg, notion_cfg = load_config()
    if not slack_cfg.get("bot_token") or not slack_cfg.get("app_token"):
        logger.error("Slack tokens not configured. Run /whip-notion-init first.")
        sys.exit(1)

    app = App(token=slack_cfg["bot_token"])
    bot_user_id = slack_cfg.get("bot_user_id", "")

    # thread_ts → Notion page_id 매핑 (메모리 캐시, 재시작 시 Notion에서 복원)
    thread_project_map = {}

    def spawn_claude(skill: str, prompt: str, slack_channel: str, thread_ts: str, notion_page_id: str = ""):
        """claude CLI를 별도 스레드에서 spawn."""
        def run():
            try:
                # Slack에 "작업 시작" 알림
                app.client.chat_postMessage(
                    channel=slack_channel,
                    thread_ts=thread_ts,
                    text=f"🔥 작업 시작합니다..."
                )

                # claude CLI 실행
                # --print: 단일 턴 실행 후 종료
                # -p: 프롬프트 전달. 슬래시 커맨드를 프롬프트로 전달하면 스킬이 트리거됨
                slash_cmd = f"/{skill.replace('-', '-')}"  # e.g. /whip, /whip-learn
                full_prompt = f"{slash_cmd} {prompt}"
                cmd = ["claude", "-p", full_prompt]
                env = os.environ.copy()
                if notion_page_id:
                    env["WHIPPER_NOTION_PAGE_ID"] = notion_page_id

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600, env=env,
                    cwd=os.path.expanduser("~")  # 유저 홈에서 실행
                )

                # 결과를 Slack 스레드에 회신
                output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
                status = "✅ 완료!" if result.returncode == 0 else "❌ 오류 발생"

                app.client.chat_postMessage(
                    channel=slack_channel,
                    thread_ts=thread_ts,
                    text=f"{status}\n\n{output}" if output else status
                )

                # Notion DB에서 방금 생성된 프로젝트의 page_id를 찾아서 스레드 매핑 업데이트
                page_id = _find_latest_notion_page(notion_cfg.get("database_id", ""))
                if page_id:
                    thread_project_map[thread_ts] = page_id

            except subprocess.TimeoutExpired:
                app.client.chat_postMessage(
                    channel=slack_channel,
                    thread_ts=thread_ts,
                    text="⏰ 작업 시간 초과 (10분). 계속하려면 이 스레드에 답장해주세요."
                )
            except Exception as e:
                logger.error(f"claude spawn error: {e}")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def detect_skill(text: str) -> str:
        """메시지 텍스트에서 스킬을 판단."""
        text_lower = text.lower()
        if "youtube.com" in text_lower or "youtu.be" in text_lower:
            return "whip-learn"
        if "/research" in text_lower or "/조사" in text_lower:
            return "whip-research"
        if "/think" in text_lower or "/분석" in text_lower:
            return "whip-think"
        if "/medical" in text_lower or "/의료" in text_lower:
            return "whip-medical"
        return "whip"

    def clean_mention(text: str) -> str:
        """@whipper 멘션 태그 제거."""
        import re
        return re.sub(r'<@[A-Z0-9]+>', '', text).strip()

    @app.event("app_mention")
    def handle_mention(event, say):
        """@whipper 멘션 처리."""
        text = clean_mention(event.get("text", ""))
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user = event.get("user", "")

        if not text:
            say(text="무엇을 도와드릴까요?", thread_ts=thread_ts)
            return

        skill = detect_skill(text)

        # 스레드에 이미 프로젝트가 매핑되어 있으면 이어서 처리
        if thread_ts in thread_project_map:
            notion_page_id = thread_project_map[thread_ts]
            spawn_claude(skill, text, channel, thread_ts, notion_page_id)
            return

        # 새 프로젝트
        slack_thread_url = f"https://slack.com/archives/{channel}/p{thread_ts.replace('.', '')}"
        spawn_claude(skill, text, channel, thread_ts)

        # claude 완료 후 Notion DB에서 최신 프로젝트 page_id를 찾아서 매핑
        # spawn_claude의 완료 콜백에서 처리됨 (아래 spawn_claude 내부 참조)
        thread_project_map[thread_ts] = "pending"

    @app.event("message")
    def handle_message(event, say):
        """스레드 메시지 처리 (멘션 없이도)."""
        # 봇 자신의 메시지 무시
        if event.get("bot_id") or event.get("user") == bot_user_id:
            return
        # 스레드 메시지만 처리
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return
        # 이 스레드에 프로젝트가 매핑되어 있으면 이어서 처리
        if thread_ts in thread_project_map:
            text = event.get("text", "")
            channel = event.get("channel", "")
            notion_page_id = thread_project_map[thread_ts]
            skill = detect_skill(text)
            spawn_claude(skill, text, channel, thread_ts, notion_page_id)

    return app, slack_cfg

def main():
    app, slack_cfg = create_app()
    handler = SocketModeHandler(app, slack_cfg["app_token"])
    logger.info("🔥 Whipper Slack Bot started (Socket Mode)")
    handler.start()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: scheduler.py 작성 (BackgroundScheduler — slack_bot.py에서 import)**

```python
#!/usr/bin/env python3
"""주기적 작업 스케줄러 — BackgroundScheduler로 slack_bot.py에 임베드."""
import subprocess
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("whipper-scheduler")

def run_todo_check():
    """whip-todo 스킬 실행."""
    try:
        result = subprocess.run(
            ["claude", "-p", "/whip-todo"],
            capture_output=True, text=True, timeout=300
        )
        logger.info(f"Todo check completed (exit={result.returncode})")
    except Exception as e:
        logger.error(f"Todo check failed: {e}")

def start_scheduler():
    """BackgroundScheduler를 시작하고 반환. 메인 스레드를 블로킹하지 않음."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_todo_check, 'interval', hours=2, id='todo_check')
    scheduler.start()
    logger.info("📋 Scheduler started (todo check every 2h)")
    return scheduler
```

그리고 `slack_bot.py`의 `main()` 함수에서 통합:
```python
def main():
    app, slack_cfg = create_app()
    # 스케줄러를 백그라운드로 시작 (메인 스레드 블로킹 안 함)
    from scheduler import start_scheduler
    sched = start_scheduler()
    # Slack Socket Mode 시작 (이것이 메인 루프)
    handler = SocketModeHandler(app, slack_cfg["app_token"])
    logger.info("🔥 Whipper Slack Bot + Scheduler started")
    handler.start()
```

- [ ] **Step 4: launchd plist 작성**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whipper.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>scripts/daemon/slack_bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/nevermind/.claude/plugins/marketplaces/whipper</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/whipper-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/whipper-daemon.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
```

- [ ] **Step 5: 테스트 작성**

```python
#!/usr/bin/env python3
"""tests/test_slack_bot.py — 데몬 유닛 테스트 (Slack API 미접속)."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "daemon"))

def test_detect_skill():
    from slack_bot import detect_skill
    assert detect_skill("https://youtube.com/watch?v=abc") == "whip-learn"
    assert detect_skill("youtu.be/abc 요약해줘") == "whip-learn"
    assert detect_skill("/research AI 트렌드") == "whip-research"
    assert detect_skill("/조사 경쟁사") == "whip-research"
    assert detect_skill("/think 이 문제 분석해봐") == "whip-think"
    assert detect_skill("/medical 두통이 심해") == "whip-medical"
    assert detect_skill("리조트 찾아줘") == "whip"

def test_clean_mention():
    from slack_bot import clean_mention
    assert clean_mention("<@U12345> 리조트 찾아줘") == "리조트 찾아줘"
    assert clean_mention("리조트 찾아줘") == "리조트 찾아줘"
    assert clean_mention("<@U12345>") == ""

if __name__ == "__main__":
    tests = [f for f in dir() if f.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            globals()[t]()
            print(f"✅ {t}")
            passed += 1
        except Exception as e:
            print(f"❌ {t}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 6: 테스트 실행**

Run: `python3 tests/test_slack_bot.py`
Expected: 2 passed, 0 failed

- [ ] **Step 7: 커밋**

```bash
git add scripts/daemon/ tests/test_slack_bot.py
git commit -m "feat: add Slack bot daemon with Socket Mode + scheduler"
```

---

## Task 6: whip-todo 스킬

Notion DB에서 queued 프로젝트를 가져와 실행, blocked 항목은 Slack 알림.

**Files:**
- Create: `commands/whip-todo.md`
- Create: `prompts/executor-todo.md`

- [ ] **Step 1: whip-todo.md 작성**

```markdown
---
description: "Review Notion todo list, run queued projects, check blocked items"
argument-hint: "[--dry-run]"
allowed-tools: [
  "Agent", "Read", "Write", "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 *:*)",
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-update-page",
  "mcp__claude_ai_Slack__slack_send_message",
  "mcp__claude_ai_Slack__slack_read_thread",
  "WebSearch", "WebFetch"
]
---

# Whip Todo — Notion 기반 프로젝트 큐 관리

## Step 1: 현황 파악

1. Read config/notion.json에서 database_id
2. notion-query-database-view로 전체 프로젝트 조회
3. 상태별 집계 출력:
   ```
   📋 Whipper Todo 현황
   진행예정: N개 | 진행중: N개 | 블락드: N개 | 완료: N개 | 드랍: N개
   ```

## Step 2: Blocked 항목 처리 (최우선)

Status=블락드인 프로젝트 각각:
1. 페이지에서 blocked 사유 확인 (notion-fetch)
2. Slack Thread URL이 있으면:
   - slack_send_message로 스레드에 알림: "🚫 유저 확인 필요: {사유}"
   - slack_read_thread로 유저 응답 확인
   - 응답 있으면: 지시에 따라 상태 변경 + 재실행
3. Slack Thread URL이 없으면: 블락 사유만 출력

## Step 3: Queued 항목 실행

Status=진행예정인 프로젝트들 (최대 3개):
1. 각 프로젝트 상태를 진행중으로 변경 (notion-update-page)
2. 하나의 메시지에 여러 Agent tool call로 병렬 디스패치:
   - 각 Agent: mode=bypassPermissions
   - prompts/executor-base.md + 해당 skill executor 포함
   - Notion page_id + 원래 명령 + 성공기준 전달
3. 3개 초과 시: 나머지는 진행예정 유지, 다음 사이클에서 처리

## Step 4: 결과 보고

처리 결과 요약 출력. --dry-run이면 계획만 출력.
```

- [ ] **Step 2: executor-todo.md 작성**

```markdown
# Todo Executor

너는 Notion 프로젝트 페이지에 기록된 작업을 실행하는 Executor다.

## 받는 정보
- Notion page_id (프로젝트 페이지)
- 원래 명령 (프롬프트)
- 성공기준 (Notion 페이지 본문에서 읽기)
- 해당 skill의 executor 프롬프트

## 실행 방법
1. notion-fetch로 프로젝트 페이지를 읽어 성공기준과 이전 컨텍스트 확인
2. executor-base.md의 절대 원칙을 따름
3. 결과를 Manager에게 반환 (Manager가 Notion에 기록)

## 유저 승인이 필요한 결정
유저 승인 없이 진행할 수 없는 사항이 있으면:
- Manager에게 "blocked" 사유를 명확히 보고
- Manager가 Notion 상태를 블락드로 변경
```

- [ ] **Step 3: 커밋**

```bash
git add commands/whip-todo.md prompts/executor-todo.md
git commit -m "feat: add whip-todo skill for Notion-based queue management"
```

---

## Task 7: 통합 + 문서 + 배포

기존 스킬 호환성 확인, plugin.json 업데이트, 커밋 + 푸시.

**Files:**
- Modify: `commands/whip-status.md` — Notion DB 조회로 변경
- Modify: `commands/whip-cancel.md` — Notion 상태 업데이트 추가
- Modify: `.claude-plugin/plugin.json`
- Modify: `.gitignore` — config/slack.json 토큰 보호

- [ ] **Step 1: whip-status.md 수정**

Notion DB 쿼리로 프로젝트 현황 표시하도록 변경. allowed-tools에 Notion MCP 추가.

- [ ] **Step 2: whip-cancel.md 수정**

active 루프 취소 시 Notion 프로젝트 상태도 "드랍"으로 업데이트.

- [ ] **Step 3: .gitignore 업데이트**

```
.gstack/
.whipper/
.claude/
__pycache__/
*.pyc
.env
.DS_Store
# 토큰이 들어갈 수 있는 설정 파일
config/slack.json
```

대신 `config/slack.json.example`을 커밋:
```json
{
  "bot_token": "xoxb-YOUR-BOT-TOKEN",
  "app_token": "xapp-YOUR-APP-TOKEN",
  "bot_user_id": "U-YOUR-BOT-USER-ID"
}
```

- [ ] **Step 4: plugin.json 업데이트**

```json
{
  "name": "whipper",
  "description": "Manager-Executor loop with Slack bot, Notion workspace, and periodic todo execution. Defines success criteria, executes via subagents, evaluates ruthlessly, iterates until passed.",
  "author": {
    "name": "nevermind"
  }
}
```

- [ ] **Step 5: 전체 테스트 실행**

```bash
python3 tests/test_notion_publisher.py
python3 tests/test_slack_bot.py
bash tests/test_core.sh
```

- [ ] **Step 6: 최종 커밋 + 푸시**

```bash
git add -A
git commit -m "feat: complete Slack + Notion integration v2"
git push origin main
```

---

## 구현 순서 요약

| Task | 내용 | 의존성 | 산출물 |
|------|------|--------|--------|
| 1 | Notion 퍼블리셔 + config | 없음 | publisher.py, fetch_iteration.py, notion.json |
| 2 | stop-hook + setup.sh 연동 | Task 1 | stop-hook 수정, state file에 notion_page_id |
| 3 | Manager/Executor 프롬프트 | Task 2 | 프롬프트 Notion 연동, allowed-tools 추가 |
| 4 | whip-notion-init | Task 1 | 초기 설정 스킬 |
| 5 | Slack 데몬 | Task 4 | slack_bot.py, scheduler.py, launchd |
| 6 | whip-todo | Task 3, 5 | Notion 큐 관리 스킬 |
| 7 | 통합 + 배포 | Task 1-6 | 테스트, 문서, 푸시 |

## 하위 호환성

- `config/notion.json`의 `database_id`가 비어있으면: **기존 로컬 파일 동작 유지**
- Manager/Executor 프롬프트에 "database_id가 없으면 콘솔 출력" 분기 포함
- Slack 데몬은 독립 프로세스 — 설치 안 해도 CLI 스킬은 그대로 동작
