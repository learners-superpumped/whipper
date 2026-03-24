# Executor — whip-research

멀티 LLM deep research 종합 조사.

## 실행 방법

1. **Gemini + ChatGPT Deep Research**: Worker 2개 병렬 디스패치
   - Worker A: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/research/gemini-research.py"` 실행
     - 결과를 {task_dir}/resources/gemini-research-raw.md에 저장
   - Worker B: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/research/openai-research.py"` 실행
     - 결과를 {task_dir}/resources/chatgpt-research-raw.md에 저장

2. **교차검증**: 두 결과에서 핵심 출처를 WebSearch/WebFetch로 직접 확인
   - 결과를 {task_dir}/resources/cross-verification.md에 저장

3. **종합 보고서**: {task_dir}/deliverables/조사-보고서.md에 저장

## 보고서 형식

```markdown
# 조사 보고서: {주제}

## 핵심 요약
## 상세 조사 결과
## 출처 불일치 사항
## 전체 출처 목록
```
