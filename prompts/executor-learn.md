# Executor — whip-learn (v3)

유튜브 영상/채널 학습 노트 생성. 주제 기반 구조, 필요한 곳에만 GIF, 토글로 보충설명.

## 단일 영상 파이프라인

순서대로 실행:

1. `GEMINI_API_KEY=$GEMINI_API_KEY python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/gemini_analyze.py" "{VIDEO_URL}" --video-id {VIDEO_ID} --title "{TITLE}" --language ko --output /tmp/yt_work/gemini`
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/extract_action_gifs.py" "{VIDEO_URL}" --gemini-result /tmp/yt_work/gemini/{VIDEO_ID}.json --video-id {VIDEO_ID} --output /tmp/yt_work/gifs`
3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/upload_images.py" /tmp/yt_work/gifs 1>/tmp/yt_work/media_urls.json 2>/dev/null`
4. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/generate_study_note.py" --gemini-result /tmp/yt_work/gemini/{VIDEO_ID}.json --media-urls /tmp/yt_work/media_urls.json --video-id {VIDEO_ID} --video-url "{VIDEO_URL}" --title "{TITLE}" --output /tmp/yt_study_notes/{VIDEO_ID}.json`

결과 JSON을 {task_dir}/deliverables/에 복사.

### Notion 발행 (--notion 사용 시)

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/render_notion_md.py" /tmp/yt_study_notes/{VIDEO_ID}.json --output /tmp/notion_md/{VIDEO_ID}.md`
2. 추적 DB에 row 등록 (register_video.py)
3. 등록된 row 페이지에 학습노트 콘텐츠를 직접 삽입 (Notion MCP update-page)
   - 페이지 최상단에 YouTube URL을 단독 줄로 삽입 → 자동 임베드
   - 그 아래에 render_notion_md.py 출력 콘텐츠 삽입
4. row 클릭 = 학습노트 열기 (Notion 앱 내 이동)

### 추적 DB 등록

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/register_video.py" \
  --title "{제목}" --channel "{채널명}" --url "{URL}" \
  --upload-date "{업로드일}" --duration {길이} --views {조회수}
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

### Phase 2: 영상별 처리 (병렬)

각 영상을 Worker 서브에이전트로 병렬 디스패치 (영상 1개 = Worker 1개)
Gemini 분석이 병목이므로 반드시 병렬. 5개씩 배치.

### Phase 3: 추적 DB 등록 + 결과 보고

각 영상 처리 완료 후:
1. 추적 DB에 row 등록
2. row 페이지에 학습노트 콘텐츠 직접 삽입
3. 전체 완료 후 결과 요약 보고:
   - 처리된 영상 목록 (제목 + URL)
   - 스킵된 영상 수
   - 전체 처리 수

전체 완료 후 {task_dir}/deliverables/index.md에 채널 종합 인덱스 생성

## 품질 원칙

1. **영상 대체** — 이것만 읽으면 영상을 안 봐도 모든 내용을 학습할 수 있어야 한다
2. **주제 기반 구조** — 타임스탬프가 아닌 내용/개념으로 섹션을 나눈다
3. **계층적 불릿포인트** — 메인 포인트 > 상세 설명 > 세부사항
4. **GIF는 필요한 곳에만** — 봐야만 이해되는 것만
5. **토글로 가독성** — 보충 설명, 배경지식, Q&A는 접어둔다
6. **빠짐없이** — 영상에서 말하거나 보여준 모든 정보가 포함되어야 한다
7. **YouTube 임베드** — 페이지 최상단에 영상을 임베드하여 바로 재생 가능

## 번역 규칙

- 한국어 영상 → 한국어 노트
- 영어 영상 → 한국어 번역 노트 (직접 인용은 영어 병기)
