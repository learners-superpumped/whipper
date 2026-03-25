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
