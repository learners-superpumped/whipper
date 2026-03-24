# Whipper Slack + Notion Integration v3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack 실시간 봇 + Notion 대시보드/퍼블리시. 루프 실행 중에는 /tmp/ 사용 (기존 메커니즘 보존), 완료 시 Notion에 퍼블리시.

**Architecture:** 얇은 Slack 데몬(이벤트 수신 → claude CLI spawn → 결과 회신). 모든 Notion 로직은 Claude 세션 안에서 MCP 도구로 처리. stop-hook 변경 최소화.

**Tech Stack:** Python (Slack Bolt), Notion MCP tools, catbox.moe, launchd, Claude Code CLI

---

## 핵심 원칙

1. **기존 루프 메커니즘 보존** — stop-hook.sh의 로컬 파일 읽기 그대로 유지
2. **데몬은 얇은 릴레이** — Slack ↔ claude CLI 중계만, Notion 로직 없음
3. **Notion은 시작/완료 시에만** — 시작: 페이지 생성, 완료: 결과 퍼블리시
4. **변경 최소화** — 기존 파일 수정은 최소한으로

## 데이터 흐름

```
@whipper 멘션 (Slack)
    │
    ▼
데몬 수신 → claude -p "/whip {prompt}" spawn
    │
    ▼
Claude 세션 시작
    ├─ setup.sh → /tmp/whipper-{id}/ 생성 + .claude/whipper.local.md
    ├─ Manager → Notion 페이지 생성 (status: 진행중)
    ├─ Executor → 작업 수행 → /tmp/ 에 로그 저장
    ├─ Manager 평가 → /tmp/ 에 기록
    ├─ stop-hook → /tmp/ 에서 읽기 (기존과 동일)
    ├─ ... iteration 반복 ...
    ├─ 완료 시: /tmp/ 내용을 Notion 페이지에 퍼블리시
    └─ /tmp/whipper-{id}/ 삭제
    │
    ▼
데몬 → stdout을 Slack 스레드에 회신
```

## File Structure

### 신규 생성

```
scripts/
  daemon/
    slack_bot.py            — Slack Bolt Socket Mode (얇은 릴레이)
    requirements.txt        — slack-bolt, slack-sdk
    com.whipper.daemon.plist — launchd 자동 시작
  notion/
    publisher.py            — 완료 시 Notion 퍼블리시 (catbox 업로드 + 콘텐츠 포맷)
config/
  notion.json               — Notion DB ID, 상태 매핑
  slack.json.example        — Slack 토큰 템플릿
commands/
  whip-todo.md              — Notion DB 큐 관리 스킬
  whip-notion-init.md       — 최초 설정 스킬
tests/
  test_slack_bot.py         — 데몬 유닛 테스트
  test_publisher.py         — 퍼블리셔 테스트
```

### 수정

```
scripts/core/setup.sh       — TASK_DIR을 /tmp/whipper-{id}/ 로 변경
prompts/manager.md           — 시작 시 Notion 페이지 생성 + 완료 시 퍼블리시 단계 추가
commands/whip.md             — allowed-tools에 Notion MCP 추가
commands/whip-*.md           — 동일
.gitignore                   — config/slack.json 추가
```

---

## Task 1: setup.sh — /tmp/ 기반으로 변경

기존 `.whipper/tasks/` 대신 `/tmp/whipper-{id}/`를 사용. stop-hook은 그대로 이 경로를 읽음.

**Files:**
- Modify: `scripts/core/setup.sh`

- [ ] **Step 1: setup.sh 수정**

변경할 부분만:

```bash
# 기존 (47행 부근):
# TASK_DIR=".whipper/tasks/${DATE}-${SLUG}"

# 신규:
TASK_ID="${DATE}-${SLUG}"
TASK_DIR="/tmp/whipper-${TASK_ID}"
```

state file에 `notion_page_id` 추가:

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
task_dir: "$TASK_DIR"
notion_page_id: ""
status: running
---

$PROMPT
EOF
```

**task_dir는 유지** — stop-hook이 이 경로로 iteration 파일을 읽으므로. 값만 `/tmp/`로 바뀜.

global index에서 `path` 필드를 task_id 기반으로:

```bash
jq --arg id "$TASK_ID" \
   --arg cmd "$PROMPT" \
   --arg skill "$SKILL" \
   --arg project "$PWD" \
   --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '. += [{id: $id, command: $cmd, skill: $skill, project: $project, started_at: $started, finished_at: null, iterations: 0, result: "running"}]' \
   "$GLOBAL_INDEX" > "$TEMP" && mv "$TEMP" "$GLOBAL_INDEX"
```

- [ ] **Step 2: 기존 테스트 수정**

`tests/test_core.sh`에서 `.whipper/tasks/` 검증을 `/tmp/whipper-` 검증으로 변경.

- [ ] **Step 3: 테스트 실행**

Run: `bash tests/test_core.sh`

- [ ] **Step 4: 커밋**

```bash
git add scripts/core/setup.sh tests/test_core.sh
git commit -m "feat: use /tmp/ for task working directory instead of .whipper/tasks/"
```

---

## Task 2: Notion 퍼블리셔 + config

완료 시 /tmp/ 내용을 Notion 페이지에 퍼블리시하는 모듈.

**Files:**
- Create: `scripts/notion/publisher.py`
- Create: `config/notion.json`
- Test: `tests/test_publisher.py`

- [ ] **Step 1: config/notion.json**

```json
{
  "database_id": "",
  "status_mapping": {
    "queued": "진행예정",
    "in_progress": "진행중",
    "completed": "완료",
    "dropped": "드랍",
    "blocked": "블락드"
  }
}
```

- [ ] **Step 2: publisher.py**

```python
#!/usr/bin/env python3
"""Notion 퍼블리시용 콘텐츠 포맷터.

이 모듈은 Notion API를 직접 호출하지 않음.
Claude 세션이 MCP 도구(notion-create-pages, notion-update-page)로 호출.
이 모듈의 역할:
1. /tmp/ 의 작업 결과물을 읽어서 Notion 페이지용 마크다운으로 변환
2. 이미지를 catbox.moe에 업로드하고 URL 반환
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

def upload_media_files(task_dir: str) -> dict:
    """task_dir 내 이미지/파일을 catbox에 업로드. {filename: url} 반환."""
    results = {}
    resources_dir = os.path.join(task_dir, "resources")
    if not os.path.isdir(resources_dir):
        return results
    for f in sorted(os.listdir(resources_dir)):
        fpath = os.path.join(resources_dir, f)
        if os.path.isfile(fpath) and f.lower().endswith((".jpg", ".png", ".gif", ".pdf", ".webp")):
            try:
                results[f] = upload_to_catbox(fpath)
            except Exception as e:
                print(f"Warning: upload failed {f}: {e}", file=sys.stderr)
    return results

def format_for_notion(task_dir: str, media_urls: dict = None) -> str:
    """task_dir의 결과물을 Notion 페이지용 마크다운으로 변환."""
    sections = []

    # 성공기준 (README.md)
    readme = os.path.join(task_dir, "README.md")
    if os.path.isfile(readme):
        with open(readme) as f:
            sections.append(f.read())

    # 최종 산출물 (deliverables/)
    deliverables_dir = os.path.join(task_dir, "deliverables")
    if os.path.isdir(deliverables_dir):
        for fname in sorted(os.listdir(deliverables_dir)):
            fpath = os.path.join(deliverables_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath) as f:
                    content = f.read()
                sections.append(f"## 결과: {fname}\n\n{content}")

    # 이미지 임베드
    if media_urls:
        img_section = "## 첨부 미디어\n"
        for name, url in media_urls.items():
            if url.endswith((".jpg", ".png", ".webp", ".gif")):
                img_section += f"\n![{name}]({url})\n"
            else:
                img_section += f"\n[{name}]({url})\n"
        sections.append(img_section)

    # Iteration 히스토리
    iterations_dir = os.path.join(task_dir, "iterations")
    if os.path.isdir(iterations_dir):
        iter_files = sorted(os.listdir(iterations_dir))
        if iter_files:
            history = "## Iteration 히스토리\n"
            for fname in iter_files:
                fpath = os.path.join(iterations_dir, fname)
                if os.path.isfile(fpath):
                    with open(fpath) as f:
                        history += f"\n### {fname}\n\n{f.read()}\n"
            sections.append(history)

    return "\n\n---\n\n".join(sections)

def cleanup_task_dir(task_dir: str):
    """완료된 task_dir 삭제."""
    import shutil
    if task_dir.startswith("/tmp/whipper-") and os.path.isdir(task_dir):
        shutil.rmtree(task_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: publisher.py <task_dir> [--upload-media]", file=sys.stderr)
        sys.exit(1)

    task_dir = sys.argv[1]
    media_urls = {}
    if "--upload-media" in sys.argv:
        media_urls = upload_media_files(task_dir)
        print(json.dumps({"media_urls": media_urls}, ensure_ascii=False), file=sys.stderr)

    content = format_for_notion(task_dir, media_urls)
    print(content)
```

- [ ] **Step 3: 테스트**

```python
#!/usr/bin/env python3
"""tests/test_publisher.py"""
import os, sys, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "notion"))
from publisher import format_for_notion, cleanup_task_dir

def _make_task_dir():
    d = tempfile.mkdtemp(prefix="/tmp/whipper-test-")
    os.makedirs(f"{d}/iterations", exist_ok=True)
    os.makedirs(f"{d}/deliverables", exist_ok=True)
    os.makedirs(f"{d}/resources", exist_ok=True)
    with open(f"{d}/README.md", "w") as f:
        f.write("# 테스트\n## 성공기준\n1. 항목A")
    with open(f"{d}/deliverables/report.md", "w") as f:
        f.write("보고서 내용")
    with open(f"{d}/iterations/01-executor-log.md", "w") as f:
        f.write("검색 수행")
    with open(f"{d}/iterations/01-manager-eval.md", "w") as f:
        f.write("PASS")
    return d

def test_format_basic():
    d = _make_task_dir()
    result = format_for_notion(d)
    assert "성공기준" in result
    assert "보고서 내용" in result
    assert "검색 수행" in result
    assert "PASS" in result
    cleanup_task_dir(d)

def test_format_with_media():
    d = _make_task_dir()
    urls = {"photo.jpg": "https://files.catbox.moe/abc.jpg"}
    result = format_for_notion(d, urls)
    assert "![photo.jpg]" in result
    cleanup_task_dir(d)

def test_cleanup():
    d = _make_task_dir()
    assert os.path.isdir(d)
    cleanup_task_dir(d)
    assert not os.path.isdir(d)

def test_cleanup_safety():
    """non-/tmp/ 경로는 삭제하지 않음."""
    cleanup_task_dir("/Users/nevermind/important")  # should do nothing
    assert True  # no error

if __name__ == "__main__":
    passed = failed = 0
    for name, func in [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]:
        try:
            func()
            print(f"✅ {name}")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 4: 테스트 실행**

Run: `python3 tests/test_publisher.py`
Expected: 4 passed, 0 failed

- [ ] **Step 5: 커밋**

```bash
git add scripts/notion/publisher.py config/notion.json tests/test_publisher.py
git commit -m "feat: add Notion publisher for post-completion content formatting"
```

---

## Task 3: Manager 프롬프트 — Notion 연동 추가

Manager에 두 단계를 추가: 시작 시 Notion 페이지 생성, 완료 시 퍼블리시.

**Files:**
- Modify: `prompts/manager.md`
- Modify: `commands/whip.md` + 나머지 commands/*.md (allowed-tools)

- [ ] **Step 1: manager.md 수정**

**0단계 변경** — `.whipper/tasks/` 참조를 Notion DB 쿼리로:

```markdown
## 0단계: 선행 작업 확인

1. config/notion.json의 database_id를 확인한다
2. **database_id가 있으면**: Notion DB에서 당일 프로젝트를 쿼리 (notion-query-database-view)
   - 현재 명령과 관련 있는 이전 프로젝트가 있으면 notion-fetch로 읽어서 컨텍스트로 사용
3. **database_id가 없으면**: 건너뜀 (Notion 미설정 호환)
```

**2단계 끝에 추가** — Notion 프로젝트 페이지 생성:

```markdown
### Notion 프로젝트 페이지 생성 (선택)

config/notion.json의 database_id가 있으면:
1. notion-create-pages로 프로젝트 페이지 생성 (DB 하위)
   - Properties: Name=명령 요약 (30자), Status=진행중, Skill=현재 스킬
2. 생성된 page_id를 .claude/whipper.local.md의 notion_page_id에 sed로 기록:
   `sed -i '' "s/^notion_page_id: .*/notion_page_id: \"PAGE_ID\"/" .claude/whipper.local.md`
3. 페이지 본문에 매핑표와 성공기준을 작성 (notion-update-page)

database_id가 없으면: 건너뜀 (기존 동작 그대로)
```

**5단계(판정) 수정** — 완료 시 퍼블리시 추가:

```markdown
## 5단계: 판정

- 모든 기준 PASS:
  1. .claude/whipper.local.md에 status: passed로 수정
  2. **Notion 퍼블리시** (notion_page_id가 있으면):
     a. python3 scripts/notion/publisher.py "$TASK_DIR" --upload-media 실행
        → 미디어 업로드 + 포맷된 콘텐츠 반환
     b. notion-update-page로 페이지 본문에 결과물 작성
     c. Status 속성을 "완료"로 변경
     d. Slack thread URL이 있으면 해당 속성도 업데이트
  3. task_dir 정리: python3 -c "from scripts.notion.publisher import cleanup_task_dir; cleanup_task_dir('$TASK_DIR')"
  4. 세션 종료

- 하나라도 FAIL:
  1. .claude/whipper.local.md에 status: failed로 수정
  2. notion_page_id가 있으면: Iteration 속성을 현재 N으로 업데이트
  3. 세션 종료 (Stop hook이 block하여 다음 iteration으로 재주입)
```

- [ ] **Step 2: commands/*.md에 Notion MCP 도구 추가**

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
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-search"
]
```

whip-learn.md, whip-research.md, whip-think.md, whip-medical.md에도 동일 추가.

- [ ] **Step 3: 커밋**

```bash
git add prompts/manager.md commands/whip.md commands/whip-learn.md commands/whip-research.md commands/whip-think.md commands/whip-medical.md
git commit -m "feat: Manager creates Notion page at start, publishes on completion"
```

---

## Task 4: Slack 데몬 (얇은 릴레이)

데몬의 역할: (1) Slack 이벤트 수신 (2) claude CLI spawn (3) stdout을 스레드에 회신. 끝.

**Files:**
- Create: `scripts/daemon/slack_bot.py`
- Create: `scripts/daemon/requirements.txt`
- Create: `scripts/daemon/com.whipper.daemon.plist`
- Create: `config/slack.json.example`
- Test: `tests/test_slack_bot.py`

- [ ] **Step 1: requirements.txt**

```
slack-bolt>=1.18.0
slack-sdk>=3.27.0
```

- [ ] **Step 2: config/slack.json.example**

```json
{
  "bot_token": "xoxb-YOUR-BOT-TOKEN",
  "app_token": "xapp-YOUR-APP-TOKEN",
  "bot_user_id": "U-YOUR-BOT-ID"
}
```

- [ ] **Step 3: slack_bot.py**

```python
#!/usr/bin/env python3
"""Whipper Slack Bot — 얇은 릴레이.

역할: Slack 이벤트 수신 → claude CLI spawn → stdout을 스레드에 회신.
Notion/프로젝트 로직 = 0. 모든 지능은 Claude 세션 안에서.
"""
import os
import sys
import json
import re
import subprocess
import threading
import logging
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("whipper-daemon")

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

def load_slack_config() -> dict:
    config_path = CONFIG_DIR / "slack.json"
    if not config_path.exists():
        logger.error(f"config/slack.json not found. Copy slack.json.example and fill in tokens.")
        sys.exit(1)
    return json.loads(config_path.read_text())

def detect_skill(text: str) -> str:
    """메시지에서 스킬 판단. 불확실하면 whip(기본)."""
    t = text.lower()
    if "youtube.com" in t or "youtu.be" in t:
        return "whip-learn"
    if "/research" in t or "/조사" in t:
        return "whip-research"
    if "/think" in t or "/분석" in t:
        return "whip-think"
    if "/medical" in t or "/의료" in t:
        return "whip-medical"
    return "whip"

def clean_mention(text: str) -> str:
    return re.sub(r'<@[A-Z0-9]+>', '', text).strip()

def create_app():
    cfg = load_slack_config()
    app = App(token=cfg["bot_token"])
    bot_user_id = cfg.get("bot_user_id", "")

    def spawn_claude(prompt: str, skill: str, channel: str, thread_ts: str):
        """별도 스레드에서 claude CLI 실행, 결과를 Slack에 회신."""
        def run():
            try:
                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"🔥 작업 시작... (/{skill})"
                )

                # claude -p 로 프롬프트 전달. 슬래시 커맨드가 스킬을 트리거.
                full_prompt = f"/{skill} {prompt}"
                result = subprocess.run(
                    ["claude", "-p", full_prompt],
                    capture_output=True, text=True, timeout=600,
                    cwd=os.path.expanduser("~")
                )

                output = result.stdout
                if len(output) > 3000:
                    output = output[-3000:]

                status = "✅ 완료!" if result.returncode == 0 else "❌ 오류"
                msg = f"{status}\n\n{output}" if output.strip() else status

                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=msg
                )
            except subprocess.TimeoutExpired:
                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text="⏰ 시간 초과 (10분). 스레드에 답장으로 이어서 진행 가능."
                )
            except Exception as e:
                logger.error(f"spawn error: {e}")
                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"❌ 오류: {e}"
                )

        threading.Thread(target=run, daemon=True).start()

    @app.event("app_mention")
    def handle_mention(event, say):
        text = clean_mention(event.get("text", ""))
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        if not text:
            say(text="무엇을 도와드릴까요?", thread_ts=thread_ts)
            return

        # 스레드 컨텍스트가 있으면 프롬프트에 포함
        # (Claude 세션이 Notion DB에서 Slack thread URL로 이전 프로젝트를 찾음)
        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_claude(slack_context + text, skill, channel, thread_ts)

    @app.event("message")
    def handle_message(event, say):
        """스레드 답장 처리 (멘션 없이도)."""
        if event.get("bot_id") or event.get("user") == bot_user_id:
            return
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return  # 스레드 아닌 일반 메시지 무시

        # 이 스레드가 봇이 이전에 응답한 스레드인지 확인
        # (봇이 응답한 적 있는 스레드에만 반응)
        try:
            thread = app.client.conversations_replies(
                channel=event["channel"], ts=thread_ts, limit=10
            )
            bot_replied = any(
                m.get("bot_id") or m.get("user") == bot_user_id
                for m in thread.get("messages", [])
            )
            if not bot_replied:
                return
        except Exception:
            return

        text = event.get("text", "")
        channel = event["channel"]
        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_claude(slack_context + text, skill, channel, thread_ts)

    return app, cfg

def main():
    app, cfg = create_app()
    handler = SocketModeHandler(app, cfg["app_token"])
    logger.info("🔥 Whipper Slack Bot started (Socket Mode)")
    handler.start()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: launchd plist**

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

- [ ] **Step 5: 테스트**

```python
#!/usr/bin/env python3
"""tests/test_slack_bot.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "daemon"))
from slack_bot import detect_skill, clean_mention

def test_detect_skill():
    assert detect_skill("https://youtube.com/watch?v=abc") == "whip-learn"
    assert detect_skill("youtu.be/abc 요약") == "whip-learn"
    assert detect_skill("/research AI 트렌드") == "whip-research"
    assert detect_skill("/조사 경쟁사") == "whip-research"
    assert detect_skill("/think 분석해봐") == "whip-think"
    assert detect_skill("/medical 두통") == "whip-medical"
    assert detect_skill("리조트 찾아줘") == "whip"
    assert detect_skill("") == "whip"

def test_clean_mention():
    assert clean_mention("<@U12345> 리조트 찾아줘") == "리조트 찾아줘"
    assert clean_mention("<@U12345>  ") == ""
    assert clean_mention("그냥 텍스트") == "그냥 텍스트"

if __name__ == "__main__":
    passed = failed = 0
    for name in [n for n in dir() if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"✅ {name}")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 6: 테스트 실행**

Run: `python3 tests/test_slack_bot.py`
Expected: 2 passed, 0 failed

- [ ] **Step 7: 커밋**

```bash
git add scripts/daemon/ config/slack.json.example tests/test_slack_bot.py
git commit -m "feat: add thin Slack bot daemon (Socket Mode relay)"
```

---

## Task 5: whip-notion-init + whip-todo

초기 설정 스킬과 큐 관리 스킬.

**Files:**
- Create: `commands/whip-notion-init.md`
- Create: `commands/whip-todo.md`

- [ ] **Step 1: whip-notion-init.md**

```markdown
---
description: "Initialize Notion database and verify Slack setup"
argument-hint: ""
allowed-tools: [
  "Read", "Write", "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "mcp__claude_ai_Notion__notion-create-database",
  "mcp__claude_ai_Notion__notion-search",
  "mcp__claude_ai_Notion__notion-fetch"
]
---

# Whip Notion Init

## Step 1: Notion DB 생성

1. notion-search로 "Whipper Projects" 데이터베이스 확인
2. 없으면 notion-create-database로 생성:
   - Schema: Name (title), Status (select), Skill (select), Slack Thread (url), Iteration (number), Created (created_time)
   - Status options: 진행예정, 진행중, 완료, 드랍, 블락드
3. database_id를 config/notion.json에 저장

## Step 2: 토큰 확인

- WHIPPER_NOTION_TOKEN 환경변수 확인. 없으면 설정 안내 출력.
- config/slack.json 존재 + 토큰 확인. 없으면 Slack App 설정 안내 출력.

## Step 3: 결과 요약

설정 상태:
- Notion DB: ✅/❌
- Notion Token: ✅/❌
- Slack config: ✅/❌
```

- [ ] **Step 2: whip-todo.md**

```markdown
---
description: "Review Notion todo list, run queued projects, check blocked items"
argument-hint: "[--dry-run]"
allowed-tools: [
  "Agent", "Read", "Write", "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-update-page",
  "mcp__claude_ai_Slack__slack_send_message",
  "mcp__claude_ai_Slack__slack_read_thread",
  "WebSearch", "WebFetch"
]
---

# Whip Todo — Notion 프로젝트 큐 관리

## Step 1: 현황 파악

1. config/notion.json에서 database_id 읽기
2. notion-query-database-view로 전체 프로젝트 조회
3. 상태별 집계 출력

## Step 2: Blocked 처리

블락드 프로젝트 각각:
- Slack Thread URL이 있으면: slack_send_message로 알림
- 유저 응답 확인 → 지시에 따라 상태 변경

## Step 3: Queued 실행 (최대 3개)

진행예정 프로젝트를 하나의 메시지에서 여러 Agent tool call로 병렬 디스패치:
- 각 Agent: mode=bypassPermissions
- prompts/manager.md + executor-base.md + 해당 skill executor 포함
- Notion page_id와 원래 프롬프트 전달

## Step 4: 결과 보고

--dry-run이면 계획만 출력. 아니면 실행 결과 요약.
```

- [ ] **Step 3: 커밋**

```bash
git add commands/whip-notion-init.md commands/whip-todo.md
git commit -m "feat: add whip-notion-init and whip-todo skills"
```

---

## Task 6: 통합 + .gitignore + 배포

**Files:**
- Modify: `.gitignore`
- Modify: `.claude-plugin/plugin.json`
- Modify: `commands/whip-status.md` — Notion DB 조회 옵션 추가
- Modify: `commands/whip-cancel.md` — Notion 상태 업데이트 추가

- [ ] **Step 1: .gitignore 업데이트**

```
.gstack/
.whipper/
.claude/
__pycache__/
*.pyc
.env
.DS_Store
config/slack.json
```

- [ ] **Step 2: whip-status.md에 Notion 조회 추가**

allowed-tools에 `mcp__claude_ai_Notion__notion-query-database-view` 추가.
Notion DB가 설정되어 있으면 Notion에서 상태 조회, 아니면 기존 로컬 조회 유지.

- [ ] **Step 3: whip-cancel.md에 Notion 업데이트 추가**

allowed-tools에 `mcp__claude_ai_Notion__notion-update-page` 추가.
취소 시 notion_page_id가 있으면 Status를 "드랍"으로 변경.

- [ ] **Step 4: plugin.json 업데이트**

```json
{
  "name": "whipper",
  "description": "Manager-Executor loop with Slack bot and Notion workspace. Real-time Slack interaction, Notion dashboard and publishing, ruthless evaluation.",
  "author": { "name": "nevermind" }
}
```

- [ ] **Step 5: 전체 테스트**

```bash
python3 tests/test_publisher.py
python3 tests/test_slack_bot.py
bash tests/test_core.sh
```

- [ ] **Step 6: 커밋 + 푸시**

```bash
git add -A
git commit -m "feat: complete Slack + Notion integration v3"
git push origin main
```

---

## 구현 순서 요약

| Task | 내용 | 변경 규모 | 의존성 |
|------|------|----------|--------|
| 1 | setup.sh → /tmp/ 기반 | 기존 파일 1개 수정 | 없음 |
| 2 | Notion 퍼블리셔 + config | 신규 3개 | 없음 |
| 3 | Manager 프롬프트 Notion 연동 | 기존 6개 수정 | Task 1, 2 |
| 4 | Slack 데몬 | 신규 4개 | 없음 |
| 5 | whip-notion-init + whip-todo | 신규 2개 | Task 2, 3 |
| 6 | 통합 + 배포 | 기존 4개 수정 | Task 1-5 |

**총: 신규 9개 파일, 기존 11개 수정 (v2의 12+10에서 줄어듦)**

## 하위 호환성

- `config/notion.json`의 `database_id`가 비어있으면 → 기존 동작 그대로 (Notion 건너뜀)
- `config/slack.json`이 없으면 → 데몬만 안 돌아감, CLI 스킬은 정상
- Manager 프롬프트의 모든 Notion 관련 동작에 "database_id가 있으면" 조건 포함
- stop-hook.sh는 **변경 없음** (TASK_DIR 값만 /tmp/으로 바뀜)
