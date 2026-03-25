# Whipper Slack+Notion v4: Slack 중간보고 + 기존일감 재개

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Whipper가 Slack 스레드에 중간 진행상황을 실시간 보고하고, 기존 일감을 재개할 수 있게 한다.

**Architecture:** `claude -p`는 Slack MCP에 접근 불가하므로, **파일 기반 Slack 브릿지** 패턴을 사용한다. Manager/Executor가 `{task_dir}/slack_messages/` 디렉토리에 메시지 파일을 쓰면, 데몬이 watchdog으로 폴링하여 Slack에 게시한다. 기존 일감 재개는 Manager Step 0에서 Notion DB를 Slack Thread URL로 정확 매칭하여 발견 시 컨텍스트를 로드한다.

**Tech Stack:** Python (slack_bot.py, slack_bridge.py), Markdown (prompts), Bash (setup.sh, stop-hook.sh), Notion MCP Tools

---

## 핵심 설계 결정

### 왜 파일 기반 브릿지인가?

`claude -p`는 headless CLI로 실행되어 Slack MCP 서버에 접근 불가 (검증 완료). 따라서:
- Manager/Executor가 `{task_dir}/slack_messages/{timestamp}.json` 파일 생성
- 데몬이 별도 스레드에서 이 디렉토리를 5초 간격 폴링
- 새 파일 발견 시 Slack API로 게시 → 파일 삭제
- 실패 시 `.failed` 확장자로 이동 (재시도 안 함)

### 메시지 파일 형식

```json
{
  "text": "📋 **성공기준 정의 완료**\n| # | 기준 |\n|---|------|\n| 1 | ... |",
  "channel": "C0AHV8FCH6V",
  "thread_ts": "1774404731.924049"
}
```

### 기존 일감 재개: Slack Thread URL 정확 매칭

Notion DB의 "Slack Thread" URL 필드로 정확 매칭. 퍼지 매칭 안 함.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/slack/bridge.py` | Create | Slack 메시지 브릿지 (폴링 + 게시) |
| `scripts/slack/post.sh` | Create | Manager/Executor용 Slack 메시지 작성 유틸리티 |
| `scripts/daemon/slack_bot.py` | Modify | 브릿지 스레드 시작, 최종 게시 축소 |
| `prompts/manager.md` | Modify | Slack 보고 + 기존일감 재개 |
| `prompts/executor-base.md` | Modify | Slack 주요 로그 보고 |
| `commands/whip.md` | Modify | allowed-tools에 post.sh 추가 |
| `scripts/core/setup.sh` | Modify | slack_messages/ 디렉토리 생성 |

---

### Task 1: Slack 메시지 브릿지 (폴링 데몬)

**Files:**
- Create: `scripts/slack/bridge.py`

- [ ] **Step 1: bridge.py 작성**

```python
#!/usr/bin/env python3
"""Slack message bridge — polls task_dir/slack_messages/ and posts to Slack."""
import os
import json
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger("whipper-bridge")


class SlackBridge:
    """Watch a directory for .json message files, post them to Slack, delete."""

    def __init__(self, slack_client, poll_interval: float = 5.0):
        self.client = slack_client
        self.poll_interval = poll_interval
        self._watchers: dict[str, threading.Thread] = {}

    def watch(self, task_dir: str, channel: str, thread_ts: str):
        """Start watching {task_dir}/slack_messages/ in background thread."""
        msg_dir = Path(task_dir) / "slack_messages"
        msg_dir.mkdir(parents=True, exist_ok=True)

        key = f"{channel}/{thread_ts}"
        if key in self._watchers and self._watchers[key].is_alive():
            return  # already watching

        def _poll():
            logger.info(f"Bridge watching: {msg_dir}")
            while True:
                try:
                    for f in sorted(msg_dir.glob("*.json")):
                        try:
                            data = json.loads(f.read_text())
                            self.client.chat_postMessage(
                                channel=data.get("channel", channel),
                                thread_ts=data.get("thread_ts", thread_ts),
                                text=data["text"],
                            )
                            f.unlink()
                            logger.info(f"Bridge posted: {f.name}")
                        except Exception as e:
                            logger.error(f"Bridge post failed: {f.name}: {e}")
                            f.rename(f.with_suffix(".failed"))
                except Exception as e:
                    logger.error(f"Bridge poll error: {e}")
                time.sleep(self.poll_interval)

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
        self._watchers[key] = t
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/slack/bridge.py
git commit -m "feat: add Slack message bridge (file-polling)"
```

---

### Task 2: Manager/Executor용 Slack 메시지 작성 유틸리티

**Files:**
- Create: `scripts/slack/post.sh`

- [ ] **Step 1: post.sh 작성**

```bash
#!/usr/bin/env bash
# Usage: post.sh <task_dir> <channel> <thread_ts> <text>
# Writes a .json file to {task_dir}/slack_messages/ for the bridge to pick up.

TASK_DIR="$1"
CHANNEL="$2"
THREAD_TS="$3"
TEXT="$4"

if [ -z "$TASK_DIR" ] || [ -z "$TEXT" ]; then
  echo "Usage: post.sh <task_dir> <channel> <thread_ts> <text>" >&2
  exit 1
fi

MSG_DIR="${TASK_DIR}/slack_messages"
mkdir -p "$MSG_DIR"

TIMESTAMP=$(python3 -c "import time; print(f'{time.time():.6f}')")
cat > "${MSG_DIR}/${TIMESTAMP}.json" << JSONEOF
{"text": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$TEXT"), "channel": "$CHANNEL", "thread_ts": "$THREAD_TS"}
JSONEOF
```

- [ ] **Step 2: 실행 권한 부여 및 테스트**

```bash
chmod +x scripts/slack/post.sh
mkdir -p /tmp/test-bridge/slack_messages
scripts/slack/post.sh /tmp/test-bridge C123 1234.5678 "테스트 메시지"
cat /tmp/test-bridge/slack_messages/*.json
# Expected: {"text": "테스트 메시지", "channel": "C123", "thread_ts": "1234.5678"}
rm -rf /tmp/test-bridge
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/slack/post.sh
git commit -m "feat: add Slack post utility for Manager/Executor"
```

---

### Task 3: setup.sh에 slack_messages 디렉토리 생성 추가

**Files:**
- Modify: `scripts/core/setup.sh`

- [ ] **Step 1: 태스크 디렉토리 생성 부분에 slack_messages/ 추가**

setup.sh에서 `mkdir -p` 하는 부분 찾아서 `slack_messages` 추가:

```bash
mkdir -p "$TASK_DIR"/{iterations,deliverables,resources,slack_messages}
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/core/setup.sh
git commit -m "feat: add slack_messages/ to task directory structure"
```

---

### Task 4: 데몬에 Slack 브릿지 통합

**Files:**
- Modify: `scripts/daemon/slack_bot.py`

- [ ] **Step 1: 브릿지 임포트 및 초기화**

`create_app()` 함수 내에서:

```python
from scripts.slack.bridge import SlackBridge
bridge = SlackBridge(app.client)
```

- [ ] **Step 2: spawn_claude에서 브릿지 시작**

`spawn_claude` 함수의 `run()` 내부, subprocess 시작 후:

```python
# task_dir 찾기: /tmp/whipper-* 에서 최신 것
import glob
task_dirs = sorted(glob.glob("/tmp/whipper-*"), key=os.path.getmtime, reverse=True)
if task_dirs:
    bridge.watch(task_dirs[0], channel, thread_ts)
```

- [ ] **Step 3: 최종 결과 게시 축소**

stdout 게시 부분을 500자 요약으로 축소:

```python
output = process.stdout.read()
if len(output) > 500:
    output = "...\n" + output[-500:]

status_emoji = "✅ 작업 완료!" if process.returncode == 0 else "❌ 오류 발생"
msg = f"{status_emoji}\n```\n{output}\n```" if output.strip() else status_emoji
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/daemon/slack_bot.py
git commit -m "feat: integrate Slack bridge into daemon"
```

---

### Task 5: whip.md에 post.sh 허용 추가

**Files:**
- Modify: `commands/whip.md`

- [ ] **Step 1: allowed-tools의 Bash 패턴에 post.sh 확인**

현재 `${CLAUDE_PLUGIN_ROOT}/scripts/*:*` 패턴이 이미 `scripts/slack/post.sh`를 포함하므로 추가 변경 불필요할 수 있음. 확인 후 필요시 추가.

- [ ] **Step 2: 커밋 (변경 있는 경우만)**

```bash
git add commands/whip.md
git commit -m "feat: ensure post.sh is in whip allowed-tools"
```

---

### Task 6: Manager 프롬프트에 Slack 보고 + 기존일감 재개 추가

**Files:**
- Modify: `prompts/manager.md`

- [ ] **Step 1: Step 0에 Slack 컨텍스트 파싱 추가**

Step 0 시작 부분에:

```markdown
## Step 0.1 — Slack 컨텍스트 파싱

프롬프트에 `[Slack thread: CHANNEL/THREAD_TS]` 패턴이 있으면:
1. CHANNEL과 THREAD_TS를 추출하여 이후 단계에서 사용
2. Slack 보고 유틸리티 경로: `${CLAUDE_PLUGIN_ROOT}/scripts/slack/post.sh`
3. 보고 방법: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/slack/post.sh "$TASK_DIR" "$CHANNEL" "$THREAD_TS" "메시지내용"`
4. 패턴이 없으면 모든 Slack 보고 단계를 건너뛴다
```

- [ ] **Step 2: Step 0에 기존 일감 재개 로직 추가**

```markdown
## Step 0.2 — 기존 일감 확인 및 재개

config/notion.json에 database_id가 있고, Slack 컨텍스트가 있으면:
1. `notion-query-database-view`로 DB 쿼리:
   - "Slack Thread" URL이 현재 thread와 일치하는 항목 (정확 매칭)
   - Status가 "진행중" 또는 "블락드"
2. 일치하는 기존 일감 발견 시:
   - `notion-fetch`로 해당 페이지 전체 내용 로드
   - `sed`로 `.claude/whipper.local.md`의 notion_page_id를 기존 값으로 업데이트
   - `sed`로 iteration을 기존 값에서 이어서 업데이트
   - Slack 보고: "📋 기존 일감 재개: {Name} (Iteration {N})"
   - 로드된 컨텍스트를 Executor 프롬프트에 포함
3. 일치하는 일감이 없으면: 새 일감으로 진행 (기존 로직)
```

- [ ] **Step 3: Step 2에 Slack 성공기준 보고 추가**

```markdown
## Step 2.5 — Slack 성공기준 보고

CHANNEL이 설정되어 있으면, post.sh로 보고:

📋 **성공기준 정의 완료**
| # | 기준 |
|---|------|
| 1 | {기준1} |
| 2 | {기준2} |
📎 Notion: {notion_page_url}
```

- [ ] **Step 4: Step 4에 Slack 평가 결과 보고 추가**

```markdown
## Step 4.5 — Slack 평가 결과 보고

CHANNEL이 설정되어 있으면, post.sh로 보고:

PASS: ✅ **전체 통과! (Iteration {N})** + 각 기준 결과
FAIL: 🔄 **재시도 필요 (Iteration {N}/{max})** + 실패 기준 + 이유
```

- [ ] **Step 5: 커밋**

```bash
git add prompts/manager.md
git commit -m "feat: add Slack reporting + task resume to Manager"
```

---

### Task 7: Executor 프롬프트에 Slack 보고 추가

**Files:**
- Modify: `prompts/executor-base.md`

- [ ] **Step 1: Slack 보고 섹션 추가**

실행 원칙 섹션 아래에:

```markdown
## Slack 실시간 보고

프롬프트에 TASK_DIR, CHANNEL, THREAD_TS가 전달된 경우, 주요 작업마다 보고:

bash ${CLAUDE_PLUGIN_ROOT}/scripts/slack/post.sh "$TASK_DIR" "$CHANNEL" "$THREAD_TS" "메시지"

보고 시점:
1. 실행 계획 수립 완료: "🔧 실행 계획: {요약}"
2. 주요 작업 완료: "📝 {작업 요약}"
3. Worker 완료: "✅ Worker: {작업명}"
4. 에러/재시도: "⚠️ {에러}, 대안 시도 중..."
```

- [ ] **Step 2: Manager의 Executor dispatch에 Slack context 전달 명시**

Manager Step 3 (Executor dispatch) 프롬프트에 추가:

```markdown
Executor에게 전달할 정보:
- TASK_DIR: {task_dir 경로}
- SLACK_CHANNEL: {channel} (있는 경우)
- SLACK_THREAD_TS: {thread_ts} (있는 경우)
- CLAUDE_PLUGIN_ROOT: {plugin root 경로}
위 값이 있으면 post.sh를 사용하여 주요 진행상황을 Slack에 보고하세요.
```

- [ ] **Step 3: 커밋**

```bash
git add prompts/executor-base.md prompts/manager.md
git commit -m "feat: add Slack reporting to Executor"
```

---

### Task 8: E2E 테스트

**Files:** None (테스트만)

- [ ] **Step 1: 데몬 재시작**

```bash
ps aux | grep "slack_bot" | grep python | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
cd /Users/nevermind/.claude/plugins/marketplaces/whipper
nohup python3 scripts/daemon/slack_bot.py > /tmp/whipper-daemon.log 2>&1 &
sleep 3 && tail -3 /tmp/whipper-daemon.log
```

- [ ] **Step 2: 단순 whip 테스트**

Slack MCP로 `@Whipper 1+1은? 답만 말해` 전송.

확인사항:
- [x] "🔥 작업 시작" (데몬)
- [ ] "📋 성공기준 정의 완료" + Notion 링크 (Manager → bridge)
- [ ] "🔧 실행 계획" (Executor → bridge)
- [ ] "✅ 전체 통과!" (Manager → bridge)
- [ ] "✅ 작업 완료!" (데몬 최종)

- [ ] **Step 3: 기존 일감 재개 테스트**

같은 스레드에서 추가 메시지 → Manager가 Notion에서 기존 일감 발견 → "📋 기존 일감 재개" 확인

- [ ] **Step 4: 실패 시 디버깅 루프**

실패한 부분의 로그 확인 → 코드 수정 → 데몬 재시작 → 재테스트.

---

## 예상 시간

| Task | 예상 |
|------|------|
| Task 1: Slack 브릿지 | 5분 |
| Task 2: post.sh 유틸리티 | 3분 |
| Task 3: setup.sh 수정 | 2분 |
| Task 4: 데몬 통합 | 5분 |
| Task 5: whip.md 확인 | 2분 |
| Task 6: Manager 프롬프트 | 10분 |
| Task 7: Executor 프롬프트 | 5분 |
| Task 8: E2E 테스트 | 15분+ |
| **합계** | **~47분** |
