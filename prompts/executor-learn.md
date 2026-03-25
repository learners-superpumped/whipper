# Executor — whip-learn

기존 `youtube-summarize` 스킬 파이프라인을 그대로 따른다. 목표는 "요약"이 아니라 **학습 노트**다.
영상/채널 URL → 자막/영상 분석 → 구조화된 학습노트 JSON → Notion 또는 마크다운 저장.

## 사용자 입력 확인

작업 시작 전에 아래를 파악한다.

1. URL: 단일 영상인지, 채널인지
2. 채널일 때 정렬: `views` 또는 `date` (기본 `date`)
3. 채널일 때 영상 수: 기본 50개
4. 저장 방식: `--notion` 이 있으면 Notion 발행, 없으면 md/json 산출물 저장

## 단일 영상 파이프라인

원본 `youtube-summarize` 흐름을 그대로 사용한다.

### Step 1: 자막 추출

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_transcript.py" \
  "{VIDEO_URL}" --output /tmp/yt_work/{VIDEO_ID}/{VIDEO_ID}_transcript.json
```

### Step 2: Gemini 분석

Gemini 키가 있으면 반드시 실행한다.

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/gemini_analyze.py" \
  "{VIDEO_URL}" --video-id {VIDEO_ID} --title "{TITLE}" --language ko \
  --output /tmp/yt_work/{VIDEO_ID}/gemini
```

Gemini 실패 시 자막 기반 파이프라인으로 계속 진행하되, 실패 사실과 폴백 이유를 로그에 남긴다.

### Step 3: 스크린샷 추출

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/capture_screenshots.py" \
  "{VIDEO_URL}" \
  --transcript /tmp/yt_work/{VIDEO_ID}/{VIDEO_ID}_transcript.json \
  --num 6 \
  --video-id {VIDEO_ID} \
  --output /tmp/yt_work/{VIDEO_ID}/screenshots
```

### Step 4: GIF 추출

GIF는 필요한 곳에만 만든다.

- Gemini 결과에 action GIF 구간이 있으면 `extract_action_gifs.py`를 우선 사용한다
- 그렇지 않으면 `extract_gifs.py`로 핵심 구간만 추출하거나, GIF가 꼭 필요 없는 영상이면 스킵한다

예시:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/extract_action_gifs.py" \
  "{VIDEO_URL}" \
  --gemini-result /tmp/yt_work/{VIDEO_ID}/gemini/{VIDEO_ID}.json \
  --video-id {VIDEO_ID} \
  --output /tmp/yt_work/{VIDEO_ID}/gifs
```

### Step 5: 미디어 업로드

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/upload_images.py" \
  /tmp/yt_work/{VIDEO_ID}/screenshots \
  /tmp/yt_work/{VIDEO_ID}/gifs \
  1>/tmp/yt_work/{VIDEO_ID}/media_urls.json 2>/dev/null
```

### Step 6: 학습노트 JSON 조립

`generate_study_note.py`에는 transcript를 반드시 넘긴다.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/generate_study_note.py" \
  --gemini-result /tmp/yt_work/{VIDEO_ID}/gemini/{VIDEO_ID}.json \
  --transcript /tmp/yt_work/{VIDEO_ID}/{VIDEO_ID}_transcript.json \
  --media-urls /tmp/yt_work/{VIDEO_ID}/media_urls.json \
  --video-id {VIDEO_ID} \
  --video-url "{VIDEO_URL}" \
  --title "{TITLE}" \
  --view-count {VIEW_COUNT} \
  --duration {DURATION} \
  --upload-date "{UPLOAD_DATE}" \
  --output /tmp/yt_study_notes/{VIDEO_ID}.json
```

### Step 7: 산출물 저장

- 최종 JSON을 `{task_dir}/deliverables/{VIDEO_ID}.json` 으로 저장
- 사용자에게 보여줄 요약/결론이 필요하면 `{task_dir}/deliverables/answer.txt` 도 함께 저장
- 스크린샷/GIF 원본은 `{task_dir}/resources/` 에 복사

### Step 8: 렌더링/발행

#### md 저장

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/render_notion_md.py" \
  /tmp/yt_study_notes/{VIDEO_ID}.json --output "{task_dir}/deliverables/{VIDEO_ID}.md"
```

#### Notion 발행 (`--notion`)

1. md 렌더링:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/render_notion_md.py" \
     /tmp/yt_study_notes/{VIDEO_ID}.json --output /tmp/notion_md/{VIDEO_ID}.md
   ```
2. 추적 DB row 등록:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/register_video.py" \
     --title "{TITLE}" \
     --channel "{CHANNEL_NAME}" \
     --url "{VIDEO_URL}" \
     --upload-date "{UPLOAD_DATE}" \
     --duration {DURATION} \
     --views {VIEW_COUNT}
   ```
3. 반환된 row page에 콘텐츠 삽입:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/publish_markdown.py" \
     "$PAGE_ID" /tmp/notion_md/{VIDEO_ID}.md --youtube-url "{VIDEO_URL}"
   ```

## 채널 파이프라인

채널 URL이면 원본 skill처럼 병렬 처리한다.

### Phase 1: 영상 목록 수집

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_channel_videos.py" \
  "{CHANNEL_URL}" --sort {views|date} --limit {N}
```

### Phase 2: 자막 배치 수집

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_transcripts.py" \
  /tmp/yt_work/channel_videos.json --output /tmp/yt_transcripts
```

### Phase 3: 중복 확인

추적 DB가 있으면 URL 목록으로 조회해서 이미 정리된 영상을 제외한다.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/query_videos.py" --urls {URL1} {URL2} ...
```

### Phase 4: 영상별 병렬 처리

- 영상 1개 = Worker 1개
- Gemini 분석이 병목이므로 5개씩 배치 병렬
- 각 Worker는 위 단일 영상 8단계를 그대로 수행

### Phase 5: 인덱스 생성

전체 완료 후 `{task_dir}/deliverables/index.md` 에 채널 종합 인덱스를 생성한다.
- 처리된 영상 목록
- 스킵된 영상 수와 이유
- 생성된 md/Notion 페이지 링크

## 품질 원칙

1. **영상 대체** — 이것만 읽으면 영상을 안 봐도 내용을 학습할 수 있어야 한다
2. **주제 기반 구조** — 타임스탬프 나열이 아니라 개념/주제 중심 재구성
3. **계층적 불릿포인트** — 메인 포인트 > 상세 설명 > 세부사항
4. **GIF/스크린샷은 필요한 곳에만** — 시각 정보가 이해에 실제로 필요할 때만
5. **빠짐없이** — 영상에서 말하거나 보여준 핵심 정보가 빠지지 않아야 한다
6. **YouTube 임베드** — Notion 발행 시 페이지 상단에서 바로 재생 가능해야 한다

## 번역 규칙

- 한국어 영상 → 한국어 노트
- 영어 영상 → 한국어 번역 노트, 직접 인용은 영어 병기
