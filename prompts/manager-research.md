# Whipper Research — Manager Supplement

`whip-research`는 일반 웹검색이 아니라 **딥 리서치 2축 + 교차검증 스킬**이다.
사용자 요청이 짧아도 아래 기준은 절대 빠지면 안 된다.

## 필수 성공기준

1. Gemini deep research 결과와 ChatGPT deep research 결과를 모두 수신한다
2. 각 raw 결과를 아래 경로에 저장한다
   - `{task_dir}/resources/gemini-research-raw.md`
   - `{task_dir}/resources/chatgpt-research-raw.md`
3. 핵심 주장/수치를 직접 교차검증하고 `resources/cross-verification.md` 에 남긴다
4. `deliverables/조사-보고서.md` 에 검증 결과와 원본 출처 링크를 정리한다
5. `deliverables/answer.txt` 에 사용자 형식의 최종 답변을 저장한다

## PASS 금지 조건

아래 중 하나라도 해당하면 PASS 금지:

- deep research raw 결과 둘 중 하나라도 없음
- cross-verification.md 없음
- 조사-보고서.md 없음
- answer.txt 없음
- 수치/사실을 원본 출처 링크 없이 단정함

## 평가 메모

- 사용자가 `한 줄`을 원해도 내부 산출물(raw + cross verification + report)은 반드시 남겨야 한다
- 최종 답변의 문장 수와 별개로, deep research 스킬의 내부 산출물 완성도를 먼저 본다
