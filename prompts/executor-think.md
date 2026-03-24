# Executor — whip-think

멀티 LLM thinking + 웹검색 종합 분석.

## 실행 방법

1. **Claude 파트**: 너(Executor) 자신이 직접 질문에 대해 깊이 사고하고 WebSearch로 근거를 찾는다
   - 결과를 {task_dir}/resources/claude-raw.md에 저장

2. **Gemini + ChatGPT 파트**: Worker 2개를 병렬 디스패치
   - Worker A: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/think/gemini-think.py"` 실행
     - stdin으로 프롬프트 전달
     - stdout 결과를 {task_dir}/resources/gemini-raw.md에 저장
   - Worker B: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/think/openai-think.py"` 실행
     - stdin으로 프롬프트 전달
     - stdout 결과를 {task_dir}/resources/chatgpt-raw.md에 저장

3. **종합**: 3개 결과를 읽고 종합 분석 보고서 작성
   - {task_dir}/deliverables/종합-분석.md에 저장

## 종합 보고서 형식

```markdown
# 종합 분석: {질문}

## 핵심 결론
## 공통 의견
## 차이점
| 관점 | Claude | Gemini | ChatGPT |
## 각 LLM별 고유 인사이트
## 종합 판단
```
