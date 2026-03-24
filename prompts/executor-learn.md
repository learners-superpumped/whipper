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

## 채널 모드

URL이 채널(@로 시작)이면:
1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/fetch_channel_videos.py" "{CHANNEL_URL}"`
2. 각 영상을 Worker 서브에이전트로 병렬 디스패치 (영상 1개 = Worker 1개)
3. 전체 완료 후 {task_dir}/deliverables/index.md에 채널 종합 인덱스 생성

## --notion 옵션

인자에 --notion이 포함되면:
1. 학습 노트 생성 완료 후
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/learn/render_notion_md.py" "{VIDEO_ID}"`
3. Notion MCP 도구로 페이지 생성
