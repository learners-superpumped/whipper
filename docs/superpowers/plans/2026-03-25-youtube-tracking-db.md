# YouTube 학습노트 통합 추적 시스템 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube 학습노트 스킬에 통합 Notion 데이터베이스 추적, 중복 방지, 메타데이터 강화(날짜/길이/조회수/YouTube 임베드)를 추가한다.

**Architecture:** 기존 whipper 플러그인의 `scripts/notion/` 에 영상 추적용 스크립트 3개를 추가하고, `api.py`에 공용 헬퍼를 추가하고, `render_notion_md.py`에 메타데이터 테이블을 강화한다. `executor-learn.md`에 중복 확인 및 등록 플로우를 단일/채널 모드 모두에 통합한다. 통합 추적 DB는 `--parent-page-id` 필수 인자로 생성한다.

**Tech Stack:** Python 3, Notion REST API, yt-dlp (기존), Notion MCP tools (DB 생성 시)

**Plugin Root:** `$HOME/.claude/plugins/marketplaces/whipper/`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/notion/api.py` | Modify | `get_video_database_id()` 공용 헬퍼 추가 |
| `scripts/notion/init_video_db.py` | Create | 추적 DB 최초 생성 (parent page ID 필수) |
| `scripts/notion/query_videos.py` | Create | 추적 DB에서 URL로 기존 영상 조회 (서버사이드 필터) |
| `scripts/notion/register_video.py` | Create | 추적 DB에 영상 메타데이터 등록 |
| `scripts/learn/render_notion_md.py` | Modify | 메타데이터 테이블 강화 + YouTube 링크 |
| `prompts/executor-learn.md` | Modify | 단일/채널 모두 중복 확인 + 등록 + YouTube embed |
| `config/notion.json` | Modify | `video_database_id` 필드 추가 (init 시 자동) |

---

### Task 1: api.py에 공용 헬퍼 추가

**Files:**
- Modify: `scripts/notion/api.py:42-46`

`get_video_database_id()` 함수를 `api.py`에 추가하여 `query_videos.py`와 `register_video.py`에서 중복 없이 사용한다.

- [ ] **Step 1: api.py에 함수 추가**

`get_database_id()` 함수 아래에 추가:

```python
def get_video_database_id() -> str | None:
    """Return video_database_id from config, or None."""
    cfg = load_config()
    return cfg.get("video_database_id")
```

- [ ] **Step 2: import 확인**

Run: `cd $HOME/.claude/plugins/marketplaces/whipper/scripts/notion && python3 -c "from api import get_video_database_id; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add scripts/notion/api.py
git commit -m "feat: add get_video_database_id() helper to Notion API module"
```

---

### Task 2: 추적 DB 초기화 스크립트 (init_video_db.py)

**Files:**
- Create: `scripts/notion/init_video_db.py`

`--parent-page-id` 필수. Notion REST API에서 workspace root에 직접 페이지를 만들 수 없으므로, 사용자가 parent page ID를 지정해야 한다.

- [ ] **Step 1: init_video_db.py 작성**

```python
#!/usr/bin/env python3
"""Create the YouTube video tracking database in Notion.

Usage: python3 init_video_db.py --parent-page-id PAGE_ID
stdout: DATABASE_ID or FAILED/NO_TOKEN/ALREADY_EXISTS
"""
import json
import sys
from pathlib import Path

# Ensure scripts/notion/ is in sys.path for api import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_headers, notion_post, load_config, CONFIG_PATH


def create_video_db(parent_page_id: str) -> str:
    headers = get_headers()
    if not headers:
        return "NO_TOKEN"

    cfg = load_config()
    if cfg.get("video_database_id"):
        return "ALREADY_EXISTS"

    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": "YouTube 학습노트 통합"}}],
        "properties": {
            "Name": {"title": {}},
            "Channel": {"rich_text": {}},
            "URL": {"url": {}},
            "Upload Date": {"date": {}},
            "Duration": {"number": {"format": "number"}},
            "Views": {"number": {"format": "number_with_commas"}},
            "Note Page": {"url": {}},
        },
    }

    resp = notion_post("/databases", body)
    if resp is None:
        return "NO_TOKEN"

    if resp.status_code == 200:
        db_id = resp.json()["id"].replace("-", "")
        # Save to config
        cfg["video_database_id"] = db_id
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        return db_id
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-page-id", required=True,
                        help="Notion page ID under which to create the tracking database")
    args = parser.parse_args()
    result = create_video_db(args.parent_page_id)
    print(result, end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 구문 확인**

Run: `cd $HOME/.claude/plugins/marketplaces/whipper/scripts/notion && python3 -c "import ast; ast.parse(open('init_video_db.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add scripts/notion/init_video_db.py
git commit -m "feat: add YouTube video tracking DB init script"
```

---

### Task 3: 영상 조회 스크립트 (query_videos.py) — 서버사이드 필터

**Files:**
- Create: `scripts/notion/query_videos.py`

URL 기반 조회는 Notion 서버사이드 필터를 사용하여 효율적으로 처리. `--all`만 전체 fetch.

- [ ] **Step 1: query_videos.py 작성**

```python
#!/usr/bin/env python3
"""Query video tracking DB to find already-summarized videos.

Usage:
  python3 query_videos.py --urls URL1 URL2 ...    # server-side filter per URL
  python3 query_videos.py --channel "채널명"        # server-side rich_text contains
  python3 query_videos.py --all                     # fetch all entries

stdout: JSON array of {url, title, channel, note_page} for matching entries
        or [] if none found
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_video_database_id, notion_post


def _parse_page(page: dict) -> dict:
    """Extract video info from a Notion page object."""
    props = page.get("properties", {})
    url_prop = props.get("URL", {}).get("url", "")
    title_prop = props.get("Name", {}).get("title", [])
    title = title_prop[0]["text"]["content"] if title_prop else ""
    channel_prop = props.get("Channel", {}).get("rich_text", [])
    channel = channel_prop[0]["text"]["content"] if channel_prop else ""
    note_prop = props.get("Note Page", {}).get("url", "")

    return {
        "url": url_prop or "",
        "title": title,
        "channel": channel,
        "note_page": note_prop or "",
    }


def _query_db(db_id: str, body: dict) -> list[dict]:
    """Run a paginated query against the tracking DB."""
    results = []
    has_more = True
    start_cursor = None

    while has_more:
        req = {**body, "page_size": 100}
        if start_cursor:
            req["start_cursor"] = start_cursor

        resp = notion_post(f"/databases/{db_id}/query", req)
        if resp is None or resp.status_code != 200:
            break

        data = resp.json()
        for page in data.get("results", []):
            results.append(_parse_page(page))

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def query_all_videos() -> list[dict]:
    """Fetch all entries from the video tracking DB."""
    db_id = get_video_database_id()
    if not db_id:
        return []
    return _query_db(db_id, {})


def query_by_urls(urls: list[str]) -> list[dict]:
    """Check which URLs already exist using server-side filters."""
    db_id = get_video_database_id()
    if not db_id:
        return []

    # Build OR filter for all URLs
    if len(urls) == 1:
        filter_body = {
            "filter": {"property": "URL", "url": {"equals": urls[0]}}
        }
    else:
        filter_body = {
            "filter": {
                "or": [
                    {"property": "URL", "url": {"equals": url}}
                    for url in urls
                ]
            }
        }

    return _query_db(db_id, filter_body)


def query_by_channel(channel: str) -> list[dict]:
    """Get all tracked videos for a channel using server-side filter."""
    db_id = get_video_database_id()
    if not db_id:
        return []

    filter_body = {
        "filter": {
            "property": "Channel",
            "rich_text": {"contains": channel},
        }
    }
    return _query_db(db_id, filter_body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="YouTube URLs to check")
    parser.add_argument("--channel", help="Channel name to filter by")
    parser.add_argument("--all", action="store_true", help="List all tracked videos")
    args = parser.parse_args()

    if args.urls:
        results = query_by_urls(args.urls)
    elif args.channel:
        results = query_by_channel(args.channel)
    else:
        results = query_all_videos()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 구문 확인**

Run: `cd $HOME/.claude/plugins/marketplaces/whipper/scripts/notion && python3 -c "import ast; ast.parse(open('query_videos.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add scripts/notion/query_videos.py
git commit -m "feat: add query_videos.py with server-side Notion filters"
```

---

### Task 4: 영상 등록 스크립트 (register_video.py)

**Files:**
- Create: `scripts/notion/register_video.py`

- [ ] **Step 1: register_video.py 작성**

```python
#!/usr/bin/env python3
"""Register a summarized video in the tracking database.

Usage: python3 register_video.py --title "제목" --channel "채널" --url "URL" \
       --upload-date "2024-01-15" --duration 600 --views 12345 \
       --note-page "https://notion.so/..."

stdout: PAGE_ID or FAILED/NO_DB/NO_TOKEN/DUPLICATE
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_video_database_id, get_headers, notion_post


def check_duplicate(db_id: str, url: str) -> bool:
    """Check if URL already exists in the tracking DB."""
    body = {
        "filter": {
            "property": "URL",
            "url": {"equals": url},
        }
    }
    resp = notion_post(f"/databases/{db_id}/query", body)
    if resp and resp.status_code == 200:
        return len(resp.json().get("results", [])) > 0
    return False


def register_video(title: str, channel: str, url: str, upload_date: str,
                    duration: int, views: int, note_page: str = "") -> str:
    headers = get_headers()
    if not headers:
        return "NO_TOKEN"

    db_id = get_video_database_id()
    if not db_id:
        return "NO_DB"

    if check_duplicate(db_id, url):
        return "DUPLICATE"

    properties = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
        "Channel": {"rich_text": [{"text": {"content": channel[:100]}}]},
        "URL": {"url": url},
        "Duration": {"number": duration},
        "Views": {"number": views},
    }

    # Parse upload_date to Notion date format (YYYY-MM-DD)
    if upload_date and len(upload_date) >= 8:
        if len(upload_date) == 8 and upload_date.isdigit():
            date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        else:
            date_str = upload_date[:10]
        properties["Upload Date"] = {"date": {"start": date_str}}

    if note_page:
        properties["Note Page"] = {"url": note_page}

    body = {"parent": {"database_id": db_id}, "properties": properties}

    resp = notion_post("/pages", body)
    if resp is None:
        return "NO_TOKEN"

    if resp.status_code == 200:
        page_id = resp.json()["id"].replace("-", "")
        return page_id
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--upload-date", default="")
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--views", type=int, default=0)
    parser.add_argument("--note-page", default="")
    args = parser.parse_args()

    result = register_video(
        args.title, args.channel, args.url,
        args.upload_date, args.duration, args.views, args.note_page
    )
    print(result, end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 구문 확인**

Run: `cd $HOME/.claude/plugins/marketplaces/whipper/scripts/notion && python3 -c "import ast; ast.parse(open('register_video.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add scripts/notion/register_video.py
git commit -m "feat: add register_video.py for tracking DB registration"
```

---

### Task 5: render_notion_md.py 메타데이터 강화

**Files:**
- Modify: `scripts/learn/render_notion_md.py:31-43`

헤더의 메타데이터를 테이블 형태로 보기 좋게 정리. YouTube 임베드는 markdown에서 처리할 수 없으므로 executor 프롬프트에서 Notion API children block으로 추가한다 (Task 6에서 정의).

- [ ] **Step 1: render_notion_md.py 헤더 수정**

현재 line 33~43을 다음으로 교체:

```python
    # Header with link
    lines.append(f"> [YouTube에서 보기]({video_url})")
    lines.append("")

    # Metadata table
    view_count = meta.get("view_count", 0)
    duration = meta.get("duration", 0)
    if duration >= 3600:
        dur_str = f"{duration // 3600}:{(duration % 3600) // 60:02d}:{duration % 60:02d}"
    elif duration:
        dur_str = f"{duration // 60}:{duration % 60:02d}"
    else:
        dur_str = "N/A"
    upload_date = meta.get("upload_date", "N/A")
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    analysis = meta.get("analysis_mode", "gemini")

    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    lines.append(f"| 업로드 | {upload_date} |")
    lines.append(f"| 길이 | {dur_str} |")
    lines.append(f"| 조회수 | {view_count:,} |")
    lines.append(f"| 분석 | {analysis} |")
    lines.append("")
    lines.append("---")
    lines.append("")
```

기존 코드 (line 34~43):
```python
    lines.append(f"> [YouTube에서 보기]({video_url})")
    view_count = meta.get("view_count", 0)
    duration = meta.get("duration", 0)
    dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"
    upload_date = meta.get("upload_date", "N/A")
    analysis = meta.get("analysis_mode", "gemini")
    lines.append(f"> 조회수: {view_count:,} | 길이: {dur_str} | 업로드: {upload_date} | 분석: {analysis}")
    lines.append("")
    lines.append("---")
    lines.append("")
```

- [ ] **Step 2: 시간 포맷 수동 검증**

duration=3700 → `1:01:40`, duration=125 → `2:05`, duration=0 → `N/A`

- [ ] **Step 3: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add scripts/learn/render_notion_md.py
git commit -m "feat: enhance metadata display with table format and hour support"
```

---

### Task 6: executor-learn.md 업데이트 — 단일+채널 모두 중복 확인/등록/YouTube 임베드

**Files:**
- Modify: `prompts/executor-learn.md`

단일 영상과 채널 모드 모두에 중복 확인 + 추적 DB 등록을 추가. YouTube embed는 Notion 페이지 생성 시 video block children으로 추가.

- [ ] **Step 1: executor-learn.md 전체 교체**

```markdown
# Executor — whip-learn

유튜브 영상/채널 학습 노트 생성.

## 단일 영상 파이프라인

순서대로 실행:

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_transcript.py" "{VIDEO_URL}"`
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/gemini_analyze.py" "{VIDEO_URL}"`
3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/capture_screenshots.py" "{VIDEO_ID}"`
4. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/extract_gifs.py" "{VIDEO_ID}"`
5. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/upload_images.py" "{VIDEO_ID}"`
6. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/generate_study_note.py" "{VIDEO_ID}"`

결과 JSON을 {task_dir}/deliverables/에 복사.
스크린샷/GIF를 {task_dir}/resources/에 복사.

### 단일 영상 추적 (--notion 사용 시)

학습노트 생성 완료 후, 추적 DB에 등록:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/register_video.py" \
  --title "{제목}" --channel "{채널명}" --url "{URL}" \
  --upload-date "{업로드일}" --duration {길이} --views {조회수} \
  --note-page "{학습노트_Notion_URL}"
```
DUPLICATE 반환 시 이미 정리된 영상. 사용자에게 알리고 계속 진행.

## 채널 모드

URL이 채널(@로 시작)이면:

### Phase 1: 영상 목록 수집 + 중복 확인

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_channel_videos.py" "{CHANNEL_URL}" --limit {N}`
2. fetch된 URL 목록으로 추적 DB 조회:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/query_videos.py" --urls {URL1} {URL2} ...
   ```
3. 조회 결과에 있는 URL을 처리 대상에서 제외
4. 보고: "이미 정리된 영상 {M}개 스킵: {제목1}, {제목2}, ..."
5. 남은 영상만 처리 대상으로 선정

### Phase 2: 영상별 처리

각 영상을 Worker 서브에이전트로 병렬 디스패치 (영상 1개 = Worker 1개)

### Phase 3: 추적 DB 등록 + 결과 보고

각 영상 처리 완료 후:
1. 학습노트 Notion 페이지 URL 확보 (--notion 옵션 사용 시)
2. 추적 DB에 등록:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/register_video.py" \
     --title "{제목}" --channel "{채널명}" --url "{URL}" \
     --upload-date "{업로드일}" --duration {길이} --views {조회수} \
     --note-page "{학습노트_Notion_URL}"
   ```
3. 전체 완료 후 결과 요약 보고:
   - 처리된 영상 목록 (제목 + URL + 학습노트 링크)
   - 스킵된 영상 수
   - 전체 처리 수

전체 완료 후 {task_dir}/deliverables/index.md에 채널 종합 인덱스 생성

## --notion 옵션

인자에 --notion이 포함되면:
1. 학습 노트 생성 완료 후
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/render_notion_md.py" "{VIDEO_ID}"`
3. Notion MCP 도구로 페이지 생성 시 **YouTube video embed를 첫 번째 블록으로 추가**:
   - `notion-create-pages`의 content 최상단에 영상 URL을 단독 줄로 삽입
   - Notion이 URL을 자동으로 video embed로 변환함
   - 예: content의 첫 줄에 `https://www.youtube.com/watch?v={VIDEO_ID}` 배치
4. 추적 DB에 등록 (register_video.py) — 단일 영상, 채널 모드 모두
```

- [ ] **Step 2: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add prompts/executor-learn.md
git commit -m "feat: add dedup + tracking + YouTube embed to both single/channel modes"
```

---

### Task 7: 통합 DB 실제 생성 (일회성)

**Files:**
- Modify: `config/notion.json` (자동 업데이트됨)

사용자가 Notion에서 parent page를 지정하여 추적 DB를 생성한다.

- [ ] **Step 1: 사용자에게 parent page ID 확인**

사용자에게 추적 DB를 어느 Notion 페이지 아래에 생성할지 물어본다.
Notion MCP의 `notion-search`로 적절한 페이지를 찾을 수 있다.

- [ ] **Step 2: init_video_db.py 실행**

Run: `cd $HOME/.claude/plugins/marketplaces/whipper/scripts/notion && python3 init_video_db.py --parent-page-id {PAGE_ID}`
Expected: 32자 DB ID 출력

- [ ] **Step 3: config 확인**

Run: `cat $HOME/.claude/plugins/marketplaces/whipper/config/notion.json`
Expected: `video_database_id` 필드 존재

- [ ] **Step 4: Commit**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper
git add config/notion.json
git commit -m "feat: register YouTube video tracking database ID"
```

---

## 동작 시나리오

### 시나리오 1: "YC 영상 최근 30개 정리해줘"
1. `fetch_channel_videos.py @ycombinator --limit 30` → 30개 영상 메타데이터
2. `query_videos.py --urls URL1 URL2 ... URL30` → 이미 정리된 URL 목록 (서버사이드 OR 필터)
3. 30개 중 이미 정리된 것 제외 → 예: 20개만 처리
4. 20개 각각에 대해 학습노트 생성 + Notion 페이지 생성 (YouTube embed 포함)
5. 각 완료 시 `register_video.py`로 추적 DB 등록
6. 결과: 20개 영상 제목 + URL + 학습노트 링크 보고

### 시나리오 2: 같은 요청 재실행
1. `fetch_channel_videos.py` → 30개
2. `query_videos.py --urls ...` → 이전 20개 URL 매칭
3. 새로 올라온 영상만 처리 (예: 2개)
4. 2개만 처리하고 나머지 28개 스킵 보고

### 시나리오 3: 단일 영상 "이 영상 정리해줘"
1. 영상 처리
2. --notion이면 Notion 페이지 생성 (YouTube embed + 메타데이터 테이블)
3. `register_video.py`로 추적 DB 등록
4. DUPLICATE이면 "이미 정리된 영상입니다" 알림
