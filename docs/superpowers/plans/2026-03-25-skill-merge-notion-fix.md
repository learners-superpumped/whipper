# whip-learn ← youtube-summarize 스킬 통합 + Notion 내부 링크 수정

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** youtube-summarize(v3) 스크립트와 프롬프트를 whip-learn에 통합하고, Notion 추적 DB의 Note Page를 relation으로 변경하여 앱 내 이동 지원.

**Architecture:** youtube-summarize 스크립트 10개를 whipper의 scripts/learn/에 덮어쓰기. executor-learn.md를 youtube-summarize 스킬 내용으로 교체. 추적 DB의 Note Page 속성을 self-relation으로 변경은 불가(다른 DB)하므로, 학습노트 페이지를 추적 DB 내부에 직접 생성하는 방식으로 전환.

**Tech Stack:** Python 3, Notion REST API, Notion MCP

**Plugin Root:** `$HOME/.claude/plugins/marketplaces/whipper/`
**Skill Root:** `$HOME/.claude/skills/youtube-summarize/`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `~/.claude/skills/youtube-summarize/` | Delete (after backup) | v3 독립 스킬 제거 |
| `scripts/learn/gemini_analyze.py` | Replace | v3 Gemini 분석 (주제 기반) |
| `scripts/learn/extract_action_gifs.py` | Create | v3 GIF 추출 (Gemini 지정 타임스탬프) |
| `scripts/learn/render_notion_md.py` | Replace | v3 sections 기반 렌더링 |
| `scripts/learn/generate_study_note.py` | Replace | v3 학습노트 JSON 조립 |
| `scripts/learn/upload_images.py` | Replace | v3 업로드 |
| `scripts/learn/fetch_transcript.py` | Replace | v3 자막 추출 |
| `scripts/learn/fetch_transcripts.py` | Replace | v3 배치 자막 |
| `scripts/learn/fetch_channel_videos.py` | Replace | v3 채널 영상 목록 |
| `scripts/learn/capture_screenshots.py` | Keep or Replace | 동일하면 유지 |
| `scripts/learn/extract_gifs.py` | Keep | 레거시 호환 (extract_action_gifs가 대체) |
| `prompts/executor-learn.md` | Replace | v3 파이프라인으로 교체 |
| `commands/whip-learn.md` | Modify | v3 스킬 설명 반영 |

---

### Task 1: youtube-summarize를 GitHub에 커밋/푸시 (백업)

**Files:**
- `~/.claude/skills/youtube-summarize/`

- [ ] **Step 1: git init + 커밋**

```bash
cd ~/.claude/skills/youtube-summarize
git init
git add -A
git commit -m "feat: youtube-summarize v3 skill - backup before merge into whip-learn"
```

- [ ] **Step 2: 원격 저장소 생성 및 푸시**

사용자에게 GitHub 리포 URL을 확인하거나, 기존 whipper 리포에 브랜치로 푸시.

---

### Task 2: v3 스크립트를 whip-learn scripts/learn/에 복사

**Files:**
- Replace: `scripts/learn/gemini_analyze.py`
- Replace: `scripts/learn/generate_study_note.py`
- Replace: `scripts/learn/render_notion_md.py`
- Replace: `scripts/learn/upload_images.py`
- Replace: `scripts/learn/fetch_transcript.py`
- Replace: `scripts/learn/fetch_transcripts.py`
- Replace: `scripts/learn/fetch_channel_videos.py`
- Create: `scripts/learn/extract_action_gifs.py`

- [ ] **Step 1: v3 스크립트 복사**

```bash
cd $HOME/.claude/plugins/marketplaces/whipper

# v3 스크립트를 whip-learn에 복사 (덮어쓰기)
cp ~/.claude/skills/youtube-summarize/scripts/gemini_analyze.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/generate_study_note.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/render_notion_md.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/upload_images.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/fetch_transcript.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/fetch_transcripts.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/fetch_channel_videos.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/extract_action_gifs.py scripts/learn/
```

- [ ] **Step 2: 스크립트 경로 수정**

v3 스크립트 내부에 `~/.claude/skills/youtube-summarize/scripts/` 하드코딩이 있으면 `${CLAUDE_PLUGIN_ROOT}/scripts/learn/`로 변경. (스크립트들은 상대경로를 사용하므로 변경 불필요할 가능성 높음)

- [ ] **Step 3: 구문 확인**

```bash
for f in scripts/learn/*.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f"; done
```

- [ ] **Step 4: Commit**

```bash
git add scripts/learn/
git commit -m "feat: replace whip-learn scripts with youtube-summarize v3"
```

---

### Task 3: executor-learn.md를 v3 파이프라인으로 교체

**Files:**
- Replace: `prompts/executor-learn.md`

- [ ] **Step 1: executor-learn.md 교체**

youtube-summarize 스킬의 파이프라인을 그대로 가져오되, 스크립트 경로를 `${CLAUDE_PLUGIN_ROOT}/scripts/learn/`로 변경. 추적 DB 등록 플로우 유지. extract_action_gifs.py 사용.

핵심 변경:
- Gemini 분석 → v3 프롬프트 (주제 기반 구조)
- GIF 추출 → extract_action_gifs.py (Gemini가 지정한 것만)
- 렌더링 → v3 render_notion_md.py (sections 기반)
- 추적 DB 등록 → register_video.py (유지)

- [ ] **Step 2: Commit**

```bash
git add prompts/executor-learn.md
git commit -m "feat: update executor-learn to v3 pipeline"
```

---

### Task 4: commands/whip-learn.md 설명 업데이트

**Files:**
- Modify: `commands/whip-learn.md`

- [ ] **Step 1: description 업데이트**

```yaml
description: "YouTube video/channel study notes (v3 - topic-based structure)"
```

allowed-tools에 `Bash(GEMINI_API_KEY=* python3 *:*)` 패턴 추가 (필요시).

- [ ] **Step 2: Commit**

```bash
git add commands/whip-learn.md
git commit -m "feat: update whip-learn command description for v3"
```

---

### Task 5: Notion 추적 DB — Note Page를 Relation으로 변경

현재 Note Page는 URL 타입이라 클릭 시 외부 링크로 열림. 학습노트 페이지를 추적 DB의 하위 페이지로 만들거나, 별도 학습노트 DB를 만들어 relation으로 연결.

**선택한 방식: 학습노트를 추적 DB 내부 페이지로 생성**

학습노트 콘텐츠를 추적 DB의 각 row 페이지 content로 직접 넣는다. 그러면 row 클릭 = 학습노트 열기. Note Page URL 속성은 불필요해짐.

- [ ] **Step 1: 기존 MFM 학습노트 콘텐츠를 추적 DB row 페이지에 삽입**

추적 DB에 이미 있는 MFM 2개 row의 page_id를 찾아서, 해당 페이지에 학습노트 콘텐츠를 `replace_content`로 삽입.

- [ ] **Step 2: executor-learn.md에서 Notion 발행 방식 변경**

`--notion` 사용 시:
1. ~~별도 페이지 생성 후 Note Page URL 저장~~ (기존)
2. → 추적 DB에 row 등록 후, 해당 row 페이지에 학습노트 콘텐츠를 직접 삽입 (새 방식)

이렇게 하면 추적 DB 테이블에서 row 클릭 = 학습노트 열기. Notion 앱 내 이동.

- [ ] **Step 3: register_video.py 수정**

등록 시 content도 함께 전달할 수 있도록 `--content-file` 옵션 추가.
또는 등록 후 page_id를 반환받아 별도로 update_page하는 방식.

- [ ] **Step 4: Note Page 속성 제거 (또는 유지)**

더 이상 필요 없으므로 숨기거나 제거.

- [ ] **Step 5: Commit**

```bash
git add scripts/notion/register_video.py prompts/executor-learn.md
git commit -m "feat: write study notes directly into tracking DB rows"
```

---

### Task 6: youtube-summarize 독립 스킬 제거

**Files:**
- Delete: `~/.claude/skills/youtube-summarize/`

- [ ] **Step 1: 스킬 디렉토리 삭제**

```bash
rm -rf ~/.claude/skills/youtube-summarize
```

- [ ] **Step 2: 확인**

`/whip-learn` 으로 동작하는지 테스트.

---

## 동작 변경 요약

| 항목 | Before | After |
|------|--------|-------|
| 스킬 경로 | `~/.claude/skills/youtube-summarize/` | `whipper/scripts/learn/` |
| 호출 방법 | `/youtube-summarize URL` | `/whip-learn URL --notion` |
| Gemini 프롬프트 | v3 주제 기반 | 동일 (v3 그대로) |
| GIF 추출 | extract_action_gifs.py | 동일 |
| Notion 학습노트 | 별도 페이지 + URL 링크 | 추적 DB row 내부에 직접 저장 |
| 학습노트 열기 | URL 클릭 → 외부 이동 | row 클릭 → Notion 앱 내 이동 |
