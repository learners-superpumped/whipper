# Executor — whip-research

Gemini, ChatGPT의 deep research 전용 모델을 **항상** 동시에 활용하여 심층 조사 후 종합한다. 멀티 LLM deep research는 선택이 아니라 **필수**다.
`whip-research`는 축소 실행 금지다. 외부 키 누락은 setup 단계에서 이미 실패했어야 하므로, Executor는 2개 deep research가 모두 있어야 한다고 가정한다.

## 실행 방법 — 항상 멀티 LLM Deep Research

### 1. Gemini + ChatGPT Deep Research 병렬 디스패치 (필수)
- Worker 2개를 **반드시** 병렬로 디스패치 (Agent 도구)
- Worker A: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/research/gemini-research.py"` 실행
  - 결과를 {task_dir}/resources/gemini-research-raw.md에 저장
- Worker B: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/research/openai-research.py"` 실행
  - 결과를 {task_dir}/resources/chatgpt-research-raw.md에 저장
- 둘 중 하나라도 빠진 상태로 조사 보고서를 완료하지 않는다

### 2. 교차검증 (필수)
- 핵심 출처를 WebSearch/WebFetch로 직접 확인
- 수치가 다른 경우 원본 출처를 직접 방문하여 확인
- 결과를 {task_dir}/resources/cross-verification.md에 저장

### 3. 종합 보고서 작성 (필수)
- {task_dir}/deliverables/조사-보고서.md 에 종합 보고서 저장 (항상)
- {task_dir}/deliverables/answer.txt 에 최종 답변 저장 (항상)
- 최종 답변 형식은 사용자 요청을 따름

### 4. Slack 보고
- 최종 답변 요약을 post.sh로 보고

## 보고서 형식

```markdown
# 조사 보고서: {주제}

## 핵심 요약
(검증된 수치 + 출처)

## 상세 조사 결과
### {카테고리}
| 수치 | 출처 | Gemini | ChatGPT | 교차검증 |
|------|------|--------|---------|----------|

## 출처 불일치 사항
(수치가 다른 경우 각각의 원본 출처와 함께 명시)

## 전체 출처 목록
1. [출처 제목](URL) — 인용 내용 요약
```

## 저장 규칙

resources/ 에 반드시 저장해야 하는 파일:
- gemini-research-raw.md — Gemini deep research 원본 (API 키 있을 때)
- chatgpt-research-raw.md — ChatGPT deep research 원본 (API 키 있을 때)
- cross-verification.md — 핵심 출처 교차검증 결과 (항상)

deliverables/ 에 반드시 저장해야 하는 파일:
- 조사-보고서.md — 종합 보고서 (항상)
- answer.txt — 사용자에게 보여줄 최종 답변 (항상)

모든 파일은 Notion에 자동 업로드된다 (인프라 처리).
