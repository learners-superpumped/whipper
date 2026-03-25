# Whipper v5: Notion REST API + 실시간 로깅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manager와 Executor 모두 Notion REST API를 직접 호출하여 페이지 생성/업데이트/로그 기록을 하고, Slack에 실시간 보고한다. MCP 의존성을 완전히 제거한다.

**Architecture:** Notion MCP 호출을 모두 Python 스크립트(requests 라이브러리)로 교체. `scripts/notion/`에 4개 유틸리티 스크립트를 만들고, Manager/Executor 프롬프트에서 `python3 스크립트` 또는 `bash 스크립트`로 호출. NOTION_TOKEN은 `config/notion.json`에 저장.

**Tech Stack:** Python 3 + requests, Bash, Notion REST API v2022-06-28

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `config/notion.json` | Modify | `token` 필드 추가 |
| `scripts/notion/api.py` | Create | 공통 Notion API 클라이언트 (token/db_id 로드, 헤더 구성) |
| `scripts/notion/create_page.py` | Replace | 페이지 생성 → page_id + URL stdout 출력 |
| `scripts/notion/update_status.py` | Create | Status/Iteration 속성 업데이트 |
| `scripts/notion/append_log.py` | Create | 페이지 본문에 로그 블록 추가 (핵심) |
| `scripts/notion/query_thread.py` | Create | Slack Thread URL로 기존 일감 검색 |
| `commands/whip.md` | Modify | Notion MCP 도구 제거 |
| `prompts/manager.md` | Modify | 모든 notion-* MCP를 Python 스크립트로 교체 |
| `prompts/executor-base.md` | Modify | Notion 로깅 추가 |

---

### Task 1: config/notion.json에 token 필드 추가 + 공통 API 모듈

**Files:**
- Modify: `config/notion.json`
- Create: `scripts/notion/api.py`

- [ ] **Step 1: notion.json에 token 필드 추가**

사용자에게 NOTION_TOKEN을 받아서 config에 저장하는 방식으로 변경.
환경변수 의존 제거 → config 파일에 직접 저장:

```json
{
  "token": "ntn_...",
  "database_id": "a640798f85fa42d582b6b45e13de569f",
  "status_mapping": {
    "queued": "진행예정",
    "in_progress": "진행중",
    "completed": "완료",
    "dropped": "드랍",
    "blocked": "블락드"
  }
}
```

먼저 현재 사용자의 Notion token을 확인:
- `NOTION_TOKEN` 또는 `WHIPPER_NOTION_TOKEN` 환경변수 체크
- 없으면 Notion integration page에서 발급 필요

- [ ] **Step 2: scripts/notion/api.py 작성**

```python
#!/usr/bin/env python3
"""Notion API 공통 모듈 — config 로드 + 인증 헤더 + 기본 요청."""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed", file=sys.stderr)
    sys.exit(1)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "notion.json"
BASE_URL = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def get_headers():
    cfg = load_config()
    token = cfg.get("token") or ""
    if not token:
        # fallback to env
        import os
        token = os.environ.get("WHIPPER_NOTION_TOKEN") or os.environ.get("NOTION_TOKEN") or ""
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": VERSION,
    }


def get_database_id():
    return load_config().get("database_id", "")


def notion_post(endpoint, body):
    headers = get_headers()
    if not headers:
        print("NO_TOKEN", end="")
        return None
    resp = requests.post(f"{BASE_URL}/{endpoint}", headers=headers, json=body, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    print(f"NOTION_ERROR:{resp.status_code}:{resp.text[:200]}", file=sys.stderr)
    return None


def notion_patch(endpoint, body):
    headers = get_headers()
    if not headers:
        return None
    resp = requests.patch(f"{BASE_URL}/{endpoint}", headers=headers, json=body, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    print(f"NOTION_ERROR:{resp.status_code}:{resp.text[:200]}", file=sys.stderr)
    return None


def notion_get(endpoint):
    headers = get_headers()
    if not headers:
        return None
    resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    return None
```

- [ ] **Step 3: 커밋**

```bash
git add config/notion.json scripts/notion/api.py
git commit -m "feat: add Notion API common module with token in config"
```

---

### Task 2: create_page.py 교체

**Files:**
- Replace: `scripts/notion/create_page.py` (기존 create_project.py를 리네임)

- [ ] **Step 1: create_page.py 작성**

```python
#!/usr/bin/env python3
"""Notion 페이지 생성. stdout: PAGE_ID URL (공백 구분)"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import get_database_id, notion_post


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--skill", default="whip")
    parser.add_argument("--slack-url", default="")
    parser.add_argument("--content", default="", help="Initial page body markdown")
    args = parser.parse_args()

    db_id = get_database_id()
    if not db_id:
        print("NO_DB", end="")
        return

    properties = {
        "Name": {"title": [{"text": {"content": args.name[:100]}}]},
        "Status": {"select": {"name": "진행중"}},
        "Skill": {"select": {"name": args.skill}},
        "Iteration": {"number": 1},
    }
    if args.slack_url:
        properties["Slack Thread"] = {"url": args.slack_url}

    body = {"parent": {"database_id": db_id}, "properties": properties}

    # 초기 본문이 있으면 children 블록 추가
    if args.content:
        body["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": args.content[:2000]}}]
                },
            }
        ]

    result = notion_post("pages", body)
    if result:
        page_id = result["id"].replace("-", "")
        url = f"https://www.notion.so/{page_id}"
        print(f"{page_id} {url}", end="")
    else:
        print("FAILED", end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 기존 create_project.py 삭제**

```bash
rm scripts/notion/create_project.py
```

- [ ] **Step 3: 테스트**

```bash
python3 scripts/notion/create_page.py --name "API Test" --skill whip
# Expected: PAGE_ID URL (또는 NO_TOKEN/NO_DB if not configured)
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/notion/create_page.py
git rm scripts/notion/create_project.py
git commit -m "feat: replace create_project.py with create_page.py using api.py"
```

---

### Task 3: append_log.py — 핵심 로깅 스크립트

**Files:**
- Create: `scripts/notion/append_log.py`

- [ ] **Step 1: append_log.py 작성**

Manager와 Executor 모두 사용하는 핵심 스크립트.
페이지 본문에 마크다운 텍스트를 블록으로 추가.

```python
#!/usr/bin/env python3
"""Notion 페이지에 로그 블록 추가.
Usage: python3 append_log.py PAGE_ID "로그 메시지"
       echo "여러 줄 로그" | python3 append_log.py PAGE_ID -
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import notion_patch


def text_to_blocks(text):
    """텍스트를 Notion 블록 배열로 변환. 2000자 단위로 분할."""
    blocks = []
    # 줄 단위로 분할해서 paragraph 블록 생성
    for chunk_start in range(0, len(text), 2000):
        chunk = text[chunk_start:chunk_start + 2000]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        })
    return blocks


def main():
    if len(sys.argv) < 3:
        print("Usage: append_log.py PAGE_ID MESSAGE_OR_DASH", file=sys.stderr)
        sys.exit(1)

    page_id = sys.argv[1]
    if sys.argv[2] == "-":
        text = sys.stdin.read()
    else:
        text = " ".join(sys.argv[2:])

    if not text.strip():
        return

    blocks = text_to_blocks(text.strip())
    result = notion_patch(f"blocks/{page_id}/children", {"children": blocks})
    if result:
        print("OK", end="")
    else:
        print("FAILED", end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/notion/append_log.py
git commit -m "feat: add append_log.py for Notion page logging"
```

---

### Task 4: update_status.py + query_thread.py

**Files:**
- Create: `scripts/notion/update_status.py`
- Create: `scripts/notion/query_thread.py`

- [ ] **Step 1: update_status.py 작성**

```python
#!/usr/bin/env python3
"""Notion 페이지 상태/속성 업데이트.
Usage: python3 update_status.py PAGE_ID --status 완료 [--iteration N]
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import notion_patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id")
    parser.add_argument("--status", help="Status select value")
    parser.add_argument("--iteration", type=int, help="Iteration number")
    args = parser.parse_args()

    properties = {}
    if args.status:
        properties["Status"] = {"select": {"name": args.status}}
    if args.iteration is not None:
        properties["Iteration"] = {"number": args.iteration}

    if not properties:
        print("NO_CHANGES", end="")
        return

    result = notion_patch(f"pages/{args.page_id}", {"properties": properties})
    print("OK" if result else "FAILED", end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: query_thread.py 작성**

```python
#!/usr/bin/env python3
"""Slack Thread URL로 기존 일감 검색.
Usage: python3 query_thread.py "https://example.slack.com/..."
stdout: PAGE_ID NAME ITERATION STATUS (탭 구분) 또는 NOT_FOUND
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import get_database_id, notion_post


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("slack_url")
    args = parser.parse_args()

    db_id = get_database_id()
    if not db_id:
        print("NOT_FOUND", end="")
        return

    # Notion DB filter: Slack Thread URL 일치 + Status가 진행중 or 블락드
    body = {
        "filter": {
            "and": [
                {"property": "Slack Thread", "url": {"equals": args.slack_url}},
                {
                    "or": [
                        {"property": "Status", "select": {"equals": "진행중"}},
                        {"property": "Status", "select": {"equals": "블락드"}},
                    ]
                },
            ]
        }
    }

    result = notion_post(f"databases/{db_id}/query", body)
    if not result or not result.get("results"):
        print("NOT_FOUND", end="")
        return

    page = result["results"][0]
    page_id = page["id"].replace("-", "")
    props = page.get("properties", {})
    name = ""
    if props.get("Name", {}).get("title"):
        name = props["Name"]["title"][0]["plain_text"]
    iteration = props.get("Iteration", {}).get("number", 1) or 1
    status = props.get("Status", {}).get("select", {}).get("name", "")
    print(f"{page_id}\t{name}\t{iteration}\t{status}", end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/notion/update_status.py scripts/notion/query_thread.py
git commit -m "feat: add update_status.py and query_thread.py for Notion REST API"
```

---

### Task 5: whip.md에서 Notion MCP 도구 제거

**Files:**
- Modify: `commands/whip.md`

- [ ] **Step 1: allowed-tools에서 Notion MCP 5줄 제거**

```diff
 allowed-tools: [
   "Agent",
   "Read",
   "Write",
   "Edit",
   "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
   "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
   "Bash(test -f *:*)",
   "Bash(sed *:*)",
   "Bash(cat *:*)",
   "Bash(mkdir *:*)",
   "Bash(chmod *:*)",
+  "Bash(rm -rf /tmp/whipper-*:*)",
+  "Bash(echo *:*)",
   "WebSearch",
-  "WebFetch",
-  "mcp__claude_ai_Notion__notion-create-pages",
-  "mcp__claude_ai_Notion__notion-update-page",
-  "mcp__claude_ai_Notion__notion-fetch",
-  "mcp__claude_ai_Notion__notion-query-database-view",
-  "mcp__claude_ai_Notion__notion-search"
+  "WebFetch"
 ]
```

- [ ] **Step 2: 커밋**

```bash
git add commands/whip.md
git commit -m "feat: remove Notion MCP tools from whip.md, add rm/echo bash patterns"
```

---

### Task 6: manager.md 전면 수정 — Notion MCP를 Python 스크립트로 교체

**Files:**
- Modify: `prompts/manager.md`

핵심 변경: 모든 `notion-*` MCP 호출을 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/*.py` 호출로 교체.

- [ ] **Step 1: 0.2단계 — 기존 일감 검색을 query_thread.py로 교체**

현재 `notion-query-database-view`와 `notion-fetch`를 사용하는 부분을:

```markdown
### 0.2 — 기존 일감 확인 및 재개

1. Slack 컨텍스트에서 Slack URL을 구성:
   `https://example.slack.com/archives/{CHANNEL}/p{THREAD_TS에서 . 제거}`

2. 기존 일감 검색:
   ```bash
   EXISTING=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/query_thread.py "SLACK_URL")
   ```
   - 결과가 `NOT_FOUND`가 아니면: PAGE_ID, NAME, ITERATION, STATUS를 탭으로 파싱
   - sed로 .claude/whipper.local.md의 notion_page_id와 iteration 업데이트
   - Slack 보고: "📋 기존 일감 재개: {NAME} (Iteration {ITERATION})"
   - 이전 성공기준을 재사용하여 3단계로 직행

3. `NOT_FOUND`이면: 새 일감으로 진행
```

- [ ] **Step 2: 2단계 — Notion 페이지 생성을 create_page.py로 교체**

```markdown
### Notion 프로젝트 페이지 생성

config/notion.json의 database_id가 있으면:
1. 페이지 생성:
   ```bash
   NOTION_RESULT=$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/create_page.py \
     --name "명령 요약 30자" --skill whip \
     --slack-url "SLACK_URL" \
     --content "성공기준 매핑표 텍스트")
   ```
2. 결과에서 PAGE_ID와 URL 파싱: `PAGE_ID=$(echo $NOTION_RESULT | cut -d' ' -f1)`, `NOTION_URL=$(echo $NOTION_RESULT | cut -d' ' -f2)`
3. sed로 .claude/whipper.local.md의 notion_page_id 업데이트

database_id가 없으면: 건너뜀
```

- [ ] **Step 3: 4단계 후 — 평가 결과를 Notion에 기록**

4단계(평가) 완료 후, 4.5단계(Slack 보고) 전에:

```markdown
### 4.3단계: Notion에 평가 결과 기록

notion_page_id가 있으면:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/append_log.py "$NOTION_PAGE_ID" \
  "## Iteration {N} 평가 결과
  {평가 테이블 텍스트}
  판정: PASS/FAIL"
```
```

- [ ] **Step 4: 5단계 — PASS 시 Notion 상태를 '완료'로 변경**

```markdown
- 모든 기준 PASS:
  1. notion_page_id가 있으면: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/update_status.py "$NOTION_PAGE_ID" --status 완료`
  2. .claude/whipper.local.md에 status: passed로 수정
  3. task_dir 정리: `rm -rf "$TASK_DIR"`
  4. 즉시 세션 종료

- 하나라도 FAIL:
  1. notion_page_id가 있으면: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/update_status.py "$NOTION_PAGE_ID" --iteration {N}`
  2. .claude/whipper.local.md에 status: failed로 수정
  3. 세션 종료
```

- [ ] **Step 5: 커밋**

```bash
git add prompts/manager.md
git commit -m "feat: replace all Notion MCP calls with Python REST API scripts in manager.md"
```

---

### Task 7: executor-base.md에 Notion 로깅 추가

**Files:**
- Modify: `prompts/executor-base.md`

- [ ] **Step 1: Notion 로깅 섹션 추가**

기존 "Slack 실시간 보고" 섹션 아래에:

```markdown
## Notion 실시간 로깅

프롬프트에 NOTION_PAGE_ID와 CLAUDE_PLUGIN_ROOT가 전달된 경우, 주요 작업마다 Notion 페이지에 로그를 남긴다:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/notion/append_log.py "$NOTION_PAGE_ID" "로그 메시지"
```

로깅 시점:
1. 실행 계획 수립 완료: "🔧 실행 계획: {요약}"
2. 주요 작업 완료: "📝 {작업 요약}"
3. 에러/재시도: "⚠️ {에러}"
4. 최종 결과: "✅ 완료: {결과 요약}" 또는 "❌ 실패: {사유}"

NOTION_PAGE_ID가 없으면 이 단계를 건너뛴다.
```

- [ ] **Step 2: Manager의 Executor dispatch에 NOTION_PAGE_ID 전달 추가**

manager.md 3단계의 Executor 프롬프트 포함 내용에 추가:
```
- NOTION_PAGE_ID: {notion_page_id} (있는 경우)
```

- [ ] **Step 3: 커밋**

```bash
git add prompts/executor-base.md prompts/manager.md
git commit -m "feat: add Notion real-time logging to Executor + pass NOTION_PAGE_ID"
```

---

### Task 8: 데몬에서 Notion 관련 코드 정리

**Files:**
- Modify: `scripts/daemon/slack_bot.py`

- [ ] **Step 1: 데몬의 pre-Claude Notion 페이지 생성 코드 제거**

이제 Manager가 직접 create_page.py를 호출하므로, 데몬에서 미리 만들 필요 없음.
`spawn_claude` 함수에서 Notion 관련 코드를 제거하고 단순하게 복원:

```python
def run():
    try:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"🔥 작업 시작... (/{skill})",
        )

        full_prompt = f"/whipper:{skill} {prompt}"
        process = subprocess.Popen(...)
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/daemon/slack_bot.py
git commit -m "fix: remove pre-Claude Notion creation from daemon (Manager handles it now)"
```

---

### Task 9: Notion token 설정 + E2E 테스트

**Files:** None (설정 + 테스트)

- [ ] **Step 1: Notion Integration Token 확인/설정**

```bash
# 현재 환경의 Notion token 확인
echo $NOTION_TOKEN
# 또는 Notion integration page에서 발급:
# https://www.notion.so/my-integrations
```

config/notion.json에 token 추가.

- [ ] **Step 2: 스크립트 단위 테스트**

```bash
# 1. 페이지 생성
python3 scripts/notion/create_page.py --name "E2E Test v5" --skill whip
# Expected: PAGE_ID URL

# 2. 로그 추가
python3 scripts/notion/append_log.py PAGE_ID "테스트 로그 메시지"
# Expected: OK

# 3. 상태 업데이트
python3 scripts/notion/update_status.py PAGE_ID --status 완료
# Expected: OK

# 4. 스레드 검색
python3 scripts/notion/query_thread.py "https://example.slack.com/archives/C0AHV8FCH6V/p1774406753288779"
# Expected: NOT_FOUND (or PAGE_ID if exists)
```

- [ ] **Step 3: 데몬 재시작 + Slack E2E**

```bash
# 데몬 재시작
ps aux | grep "slack_bot" | grep python | grep -v grep | awk '{print $2}' | xargs kill
cd $HOME/.claude/plugins/marketplaces/whipper
nohup python3 scripts/daemon/slack_bot.py > /tmp/whipper-daemon.log 2>&1 &
```

Slack MCP로 `@Whipper 5+5는? 답만` 전송.

확인사항:
- [ ] "🔥 작업 시작" (데몬)
- [ ] "📋 성공기준 정의 완료" + Notion 링크 (Manager → bridge)
- [ ] Notion 페이지에 성공기준 기록됨
- [ ] "🔧 실행 계획" (Executor → bridge)
- [ ] Notion 페이지에 실행 로그 기록됨
- [ ] "✅ 전체 통과!" + Notion 링크 (Manager → bridge)
- [ ] Notion 페이지 Status가 "완료"로 변경됨
- [ ] "✅ 작업 완료!" (데몬 최종) — 30분 타임아웃 전에 도착
- [ ] claude -p 프로세스가 5분 내에 종료됨

- [ ] **Step 4: 실패 시 디버깅**

디버깅 루프: 로그 확인 → 코드 수정 → 데몬 재시작 → 재테스트.

---

## 예상 시간

| Task | 예상 |
|------|------|
| Task 1: config + api.py | 3분 |
| Task 2: create_page.py | 3분 |
| Task 3: append_log.py | 3분 |
| Task 4: update_status + query_thread | 5분 |
| Task 5: whip.md MCP 제거 | 2분 |
| Task 6: manager.md 전면 수정 | 10분 |
| Task 7: executor-base.md Notion 로깅 | 5분 |
| Task 8: 데몬 정리 | 3분 |
| Task 9: Token 설정 + E2E | 15분+ |
| **합계** | **~49분** |
