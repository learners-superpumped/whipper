# Whipper Think — Manager Supplement

`whip-think`는 일반 질의응답이 아니라 **멀티 LLM 비교 스킬**이다.
사용자 질문이 단순하더라도 아래 기준은 절대 빠지면 안 된다.

## 필수 성공기준

1. Claude, Gemini, ChatGPT 3개 응답을 모두 수신한다
2. 각 raw 결과를 아래 경로에 저장한다
   - `{task_dir}/resources/claude-raw.md`
   - `{task_dir}/resources/gemini-raw.md`
   - `{task_dir}/resources/chatgpt-raw.md`
3. `deliverables/종합-분석.md` 에 공통점/차이점/근거를 종합한다
4. `deliverables/answer.txt` 에 사용자 형식의 최종 답변을 저장한다

## PASS 금지 조건

아래 중 하나라도 해당하면 PASS 금지:

- 세 LLM 중 하나라도 빠짐
- raw 파일 중 하나라도 없음
- 종합-분석.md 없음
- answer.txt 없음
- 최종 답변이 세 LLM 비교를 거치지 않고 단일 모델 판단만 반영함

## 평가 메모

- 사용자가 `답만`을 원해도 내부 산출물(raw + synthesis)은 반드시 남겨야 한다
- 최종 한 줄 답변은 간결할 수 있지만, Manager 평가는 반드시 3개 raw 결과와 종합 파일을 기준으로 한다
