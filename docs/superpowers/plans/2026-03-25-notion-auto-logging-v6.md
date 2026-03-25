# Whipper v6: Notion 자동 로깅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notion 로깅을 LLM 프롬프트 의존에서 인프라 자동화로 전환. task_dir의 모든 파일을 자동으로 Notion에 업로드한다.

**Architecture:** 데몬이 PASS 감지 시 `upload_task.py`를 호출하여 task_dir 전체 내용(성공기준, 실행계획, 실행로그, 매니저평가, 결과물)을 Notion 페이지에 일괄 업로드. stop-hook에서도 FAIL iteration마다 해당 iteration 로그를 업로드. LLM은 Notion append_log를 안 써도 됨.

**Tech Stack:** Python 3 + requests (Notion REST API), Bash (stop-hook)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/notion/upload_task.py` | Create | task_dir 전체를 Notion 페이지에 업로드 |
| `scripts/daemon/slack_bot.py` | Modify | PASS 감지 후 upload_task.py 실행 |
| `hooks/stop-hook.sh` | Modify | FAIL iteration 시 iteration 로그 업로드 |
| `prompts/executor-base.md` | Modify | Notion 로깅 지시 제거 |
| `prompts/manager.md` | Modify | Notion append_log 지시 제거, 4.3단계 삭제 |

---

### Task 1: upload_task.py — task_dir 전체를 Notion에 업로드

**Files:**
- Create: `scripts/notion/upload_task.py`

- [ ] **Step 1: upload_task.py 작성**

```python
#!/usr/bin/env python3
"""Upload entire task_dir contents to a Notion page.
Usage: python3 upload_task.py PAGE_ID TASK_DIR [--iteration N]
  --iteration N: only upload iteration N files (for FAIL mid-loop)
  without --iteration: upload everything (for final PASS)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import notion_patch


def text_to_blocks(text, max_len=2000):
    blocks = []
    for i in range(0, len(text), max_len):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[i:i+max_len]}}]
            },
        })
    return blocks


def heading_block(text, level=2):
    h_type = f"heading_{level}"
    return {
        "object": "block",
        "type": h_type,
        h_type: {
            "rich_text": [{"type": "text", "text": {"content": text[:100]}}]
        },
    }


def divider_block():
    return {"object": "block", "type": "divider", "divider": {}}


def upload_file(page_id, heading, content):
    """Append a heading + content blocks to the page."""
    if not content.strip():
        return
    blocks = [heading_block(heading), *text_to_blocks(content), divider_block()]
    # Notion API limits 100 blocks per request
    for i in range(0, len(blocks), 100):
        notion_patch(f"blocks/{page_id}/children", {"children": blocks[i:i+100]})


def upload_all(page_id, task_dir):
    """Upload everything in task_dir to the Notion page."""
    td = Path(task_dir)

    # 1. README.md (성공기준)
    readme = td / "README.md"
    if readme.exists():
        upload_file(page_id, "📋 성공기준", readme.read_text())

    # 2. iterations/ (실행계획, 실행로그, 매니저평가)
    iters_dir = td / "iterations"
    if iters_dir.exists():
        for f in sorted(iters_dir.glob("*.md")):
            label = f.stem  # e.g. "01-execution-plan"
            upload_file(page_id, f"📝 {label}", f.read_text())

    # 3. deliverables/ (결과물)
    deliv_dir = td / "deliverables"
    if deliv_dir.exists():
        for f in sorted(deliv_dir.glob("*")):
            if f.is_file():
                try:
                    content = f.read_text()
                except UnicodeDecodeError:
                    content = f"(바이너리 파일: {f.name}, {f.stat().st_size} bytes)"
                upload_file(page_id, f"📦 결과물: {f.name}", content)


def upload_iteration(page_id, task_dir, iteration):
    """Upload only a specific iteration's files."""
    td = Path(task_dir) / "iterations"
    prefix = f"{iteration:02d}-"
    for f in sorted(td.glob(f"{prefix}*.md")):
        upload_file(page_id, f"📝 Iteration {iteration}: {f.stem}", f.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id")
    parser.add_argument("task_dir")
    parser.add_argument("--iteration", type=int, default=None)
    args = parser.parse_args()

    if args.iteration:
        upload_iteration(args.page_id, args.task_dir, args.iteration)
    else:
        upload_all(args.page_id, args.task_dir)
    print("OK", end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 테스트**

```bash
# 기존 테스트 Notion 페이지에 업로드 테스트
# 먼저 테스트용 task_dir 생성
mkdir -p /tmp/whipper-test/{iterations,deliverables}
echo "# 성공기준\n1. 테스트" > /tmp/whipper-test/README.md
echo "# 실행계획\n- Step 1: 검색" > /tmp/whipper-test/iterations/01-execution-plan.md
echo "# 매니저 평가\n| 기준 | 판정 |\n|---|---|\n| 1 | PASS |" > /tmp/whipper-test/iterations/01-manager-eval.md
echo "# 결과\n테스트 결과입니다." > /tmp/whipper-test/deliverables/result.md

# 기존 테스트 페이지 ID 사용 (E2E Test 페이지)
python3 scripts/notion/upload_task.py 32ed94f326ee81e190c0ecfa374422ef /tmp/whipper-test
# Expected: OK

rm -rf /tmp/whipper-test
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/notion/upload_task.py
git commit -m "feat: add upload_task.py for automatic Notion logging"
```

---

### Task 2: 데몬에서 PASS 감지 후 자동 Notion 업로드

**Files:**
- Modify: `scripts/daemon/slack_bot.py:136-162`

- [ ] **Step 1: PASS 감지 시 upload_task.py 실행**

데몬의 `pass_detected_at` 감지 직후, force-kill 전에 Notion 업로드를 실행한다.
state 파일은 이미 삭제됐으므로, state 파일에서 notion_page_id를 읽을 수 없다. 대신 task_dir에서 찾거나, state 파일이 삭제되기 전에 page_id를 캐시한다.

**핵심 변경**: PASS 감지 시 `~/.claude/whipper.local.md`가 이미 삭제됐으므로, state 파일이 존재할 때 미리 notion_page_id를 읽어둔다:

```python
# 폴링 루프 상단 (state_file_ever_existed 추적 부근):
notion_page_id = ""
# ...
if state_file.exists():
    state_file_ever_existed = True
    # notion_page_id 캐시 (state 파일이 삭제되기 전에)
    try:
        content = state_file.read_text()
        for line in content.split('\n'):
            if line.startswith('notion_page_id:'):
                pid = line.split(':', 1)[1].strip().strip('"')
                if pid:
                    notion_page_id = pid
    except:
        pass
```

그리고 PASS 감지 후:

```python
if pass_detected_at and (time.time() - pass_detected_at > 60):
    # Notion에 task_dir 전체 업로드
    if notion_page_id:
        try:
            newest_task = max(
                [d for d in glob.glob("/tmp/whipper-2026-*") if os.path.isdir(d)],
                key=os.path.getmtime, default=None
            )
            if newest_task:
                subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "notion" / "upload_task.py"),
                     notion_page_id, newest_task],
                    timeout=30,
                )
                logger.info(f"Notion upload complete: {notion_page_id}")
        except Exception as e:
            logger.error(f"Notion upload failed: {e}")
    # 그 후 force-kill
    logger.info("Force-killing claude after PASS grace period.")
    process.kill()
    break
```

- [ ] **Step 2: SCRIPTS_DIR 변수 추가**

데몬 파일 상단에:

```python
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/daemon/slack_bot.py
git commit -m "feat: auto-upload task_dir to Notion on PASS detection"
```

---

### Task 3: stop-hook에서 FAIL iteration 로그 업로드

**Files:**
- Modify: `hooks/stop-hook.sh:56-100`

- [ ] **Step 1: FAIL 시 iteration 로그를 Notion에 업로드**

stop-hook의 "Status: failed or running → block and re-inject" 섹션에서, re-injection 전에 Notion 업로드를 추가:

```bash
# Status: failed or running → block and re-inject
NEXT_ITERATION=$((ITERATION + 1))

# Notion에 현재 iteration 로그 업로드 (비동기, 실패해도 무시)
NOTION_PAGE_ID=$(echo "$FRONTMATTER" | grep '^notion_page_id:' | sed 's/notion_page_id: *//' | sed 's/^"\(.*\)"$/\1/')
if [[ -n "$NOTION_PAGE_ID" ]] && [[ -d "$TASK_DIR/iterations" ]]; then
  python3 "$PLUGIN_ROOT/scripts/notion/upload_task.py" "$NOTION_PAGE_ID" "$TASK_DIR" --iteration "$ITERATION" 2>/dev/null &
fi
```

이걸 `NEXT_ITERATION` 계산 직후, prompt 추출 전에 넣는다.

- [ ] **Step 2: PLUGIN_ROOT를 앞쪽에서 설정**

현재 PLUGIN_ROOT는 status: passed 블록 안에서만 설정됨. FAIL 블록에서도 쓸 수 있게 위치를 위로 올린다:

```bash
# Parse 직후, status 체크 전에:
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
```

- [ ] **Step 3: 커밋**

```bash
git add hooks/stop-hook.sh
git commit -m "feat: auto-upload iteration logs to Notion on FAIL in stop-hook"
```

---

### Task 4: 프롬프트에서 Notion 수동 로깅 지시 제거

**Files:**
- Modify: `prompts/executor-base.md`
- Modify: `prompts/manager.md`

- [ ] **Step 1: executor-base.md에서 "Notion 상세 로깅" 섹션 전체 제거**

기존 "Notion 상세 로깅" 섹션을 짧은 안내로 교체:

```markdown
## Notion 로깅

Notion 로깅은 인프라가 자동으로 처리한다. Executor는 Notion에 직접 기록할 필요 없다.
iterations/ 디렉토리에 실행계획과 로그를 파일로 잘 기록하면, 자동으로 Notion에 업로드된다.
```

- [ ] **Step 2: manager.md에서 4.3단계(평가 결과 Notion 기록) 제거**

4.3단계 전체를 제거하고 짧은 안내로 교체:

```markdown
### 4.3단계: (자동) Notion 기록

Notion 로깅은 인프라가 자동 처리한다. iterations/ 디렉토리의 파일을 잘 기록하면 됨.
Manager는 append_log.py를 직접 호출하지 않는다.
```

- [ ] **Step 3: manager.md 5단계 PASS에서 Notion update_status 제거**

5단계 PASS의 `update_status.py --status 완료` 호출도 제거. 데몬이 upload 시 함께 처리:

```markdown
- 모든 기준 PASS:
  1. **state 파일 삭제**: `rm -f .claude/whipper.local.md`
  2. **즉시 세션 종료** — 이 2단계만. Notion/cleanup은 인프라가 처리.
```

- [ ] **Step 4: 캐시 동기화**

```bash
rm -rf ~/.claude/plugins/cache/whipper/whipper/unknown
cp -r ~/.claude/plugins/marketplaces/whipper ~/.claude/plugins/cache/whipper/whipper/unknown
```

- [ ] **Step 5: 커밋**

```bash
git add prompts/executor-base.md prompts/manager.md
git commit -m "feat: remove manual Notion logging from prompts (infra handles it)"
```

---

### Task 5: 데몬에서 Notion status 업데이트도 자동화

**Files:**
- Modify: `scripts/daemon/slack_bot.py`
- Modify: `scripts/notion/upload_task.py`

- [ ] **Step 1: upload_task.py에 --status 옵션 추가**

```python
parser.add_argument("--status", default=None, help="Update page Status property")
# ...
if args.status:
    from api import notion_patch as np
    np(f"pages/{args.page_id}", {
        "properties": {"Status": {"select": {"name": args.status}}}
    })
```

- [ ] **Step 2: 데몬에서 upload 시 --status 완료 추가**

```python
subprocess.run(
    [sys.executable, str(SCRIPTS_DIR / "notion" / "upload_task.py"),
     notion_page_id, newest_task, "--status", "완료"],
    timeout=30,
)
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/notion/upload_task.py scripts/daemon/slack_bot.py
git commit -m "feat: auto-update Notion status to 완료 on PASS upload"
```

---

### Task 6: E2E 테스트

- [ ] **Step 1: 클린 재시작**

```bash
ps aux | grep "slack_bot" | grep python | grep -v grep | awk '{print $2}' | xargs kill
rm -f ~/.claude/whipper.local.md
rm -rf /tmp/whipper-2026-03-25-*
# 캐시 동기화
rm -rf ~/.claude/plugins/cache/whipper/whipper/unknown
cp -r ~/.claude/plugins/marketplaces/whipper ~/.claude/plugins/cache/whipper/whipper/unknown
# 데몬 시작
cd $HOME/.claude/plugins/marketplaces/whipper
nohup python3 scripts/daemon/slack_bot.py > /tmp/whipper-daemon.log 2>&1 &
```

- [ ] **Step 2: Slack E2E 테스트**

`@Whipper 오늘 서울 날씨 알려줘` 전송.

확인:
- [ ] Slack: 성공기준 + Notion 링크
- [ ] Slack: 실행계획 보고
- [ ] Slack: 작업 완료
- [ ] Notion: 성공기준 (create_page.py가 기록)
- [ ] Notion: 실행계획 (upload_task.py가 자동 업로드)
- [ ] Notion: 매니저 평가 (upload_task.py가 자동 업로드)
- [ ] Notion: 결과물 (upload_task.py가 자동 업로드)
- [ ] Notion: Status = "완료"
- [ ] task_dir이 삭제되기 전에 업로드 완료

---

## 예상 시간

| Task | 예상 |
|------|------|
| Task 1: upload_task.py | 5분 |
| Task 2: 데몬 PASS 업로드 | 5분 |
| Task 3: stop-hook FAIL 업로드 | 3분 |
| Task 4: 프롬프트 정리 | 3분 |
| Task 5: status 자동화 | 2분 |
| Task 6: E2E 테스트 | 10분 |
| **합계** | **~28분** |
