# Executor — whip-think

동일한 질문을 **Claude, Gemini, ChatGPT 3개 LLM에 동시에 보내고**, 웹검색을 포함하여 결과를 종합 분석한다. 멀티 LLM은 선택이 아니라 **필수**.

## 실행 방법 — 항상 3개 LLM 병렬

### 1. Claude 파트 (Executor 직접 수행)
- Executor 자체가 직접 thinking + WebSearch 수행
- 결과를 {task_dir}/resources/claude-raw.md에 저장

### 2. Gemini + ChatGPT Worker 병렬 디스패치 (필수)
- Worker 2개를 **반드시** 병렬로 디스패치 (Agent 도구)
- Worker A: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/think/gemini-think.py"` → {task_dir}/resources/gemini-raw.md
- Worker B: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/think/openai-think.py"` → {task_dir}/resources/chatgpt-raw.md
- API 키가 없는 LLM은 해당 Worker를 스킵하되, **가용한 LLM은 반드시 실행**
- 1개만 가용해도 Claude + 해당 LLM 2개로 진행

### 3. 종합 분석 보고서 작성 (필수)
- 3개(또는 가용한) LLM의 결과를 비교/종합
- {task_dir}/deliverables/종합-분석.md 작성 (항상)
- {task_dir}/deliverables/answer.txt 에 최종 답변 저장
- 최종 답변 형식은 사용자 요청을 따름 ("답만" → 한 줄, "분석해줘" → 보고서)

### 4. Slack 보고
- 최종 답변 요약을 post.sh로 보고

## 종합 보고서 형식

```markdown
# 종합 분석: {질문}

## 핵심 결론
(3개 LLM 의견 종합)

## 공통 의견
(3개 모두 동의하는 부분)

## 차이점
| 관점 | Claude | Gemini | ChatGPT |
|------|--------|--------|---------|

## 각 LLM별 고유 인사이트
### Claude
### Gemini
### ChatGPT

## 종합 판단
(근거 기반 최종 판단)
```

## 저장 규칙

resources/ 에 반드시 저장해야 하는 파일:
- claude-raw.md — Claude 사고 결과 원본
- gemini-raw.md — Gemini 응답 원본 (API 키 있을 때)
- chatgpt-raw.md — ChatGPT 응답 원본 (API 키 있을 때)

deliverables/ 에 반드시 저장해야 하는 파일:
- 종합-분석.md — 3개 LLM 비교 종합 보고서 (항상)
- answer.txt — 사용자에게 보여줄 최종 답변 (항상)

모든 파일은 Notion에 자동 업로드된다 (인프라 처리).
