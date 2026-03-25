# Manager Multi-LLM Review Proposal

## 결론

Manager를 통째로 다른 LLM으로 바꾸는 것보다, **Claude Manager + 외부 LLM 비평가(critic)** 구조가 현재 Whipper에는 더 맞다.

가장 품질 상승 폭이 큰 지점은 `Executor 완료 후, Manager PASS/FAIL 직전`이다.

## 왜 전면 교체보다 비평가가 맞는가

- 현재 loop 상태, stop hook, state file, Slack/Notion 보고 문구는 Claude Manager 전제를 많이 깔고 있다
- Manager를 통째로 Codex/Gemini로 바꾸면 프롬프트 편차와 운영 복잡도가 같이 커진다
- 반면 평가 단계에 critic을 붙이면, orchestration은 유지하면서도 판정 품질만 높일 수 있다

## 추천 삽입 지점

### 1. 성공기준 정의 직후: `criteria sanity review`

목적:
- 기준 누락
- 과도한 완화
- 사용자 요청과 다른 성공기준

권장 모델:
- Codex 또는 Gemini Flash 급의 빠른 모델

출력:
- `iterations/{NN}-criteria-review.md`

효과:
- 초기 설계 실수를 줄인다
- 비용은 낮지만, 최종 품질 상승 폭은 중간 정도다

### 2. Executor 완료 직후, Manager 판정 직전: `adversarial review`

목적:
- PASS 오판 방지
- 출처 누락/형식 위반/닫힌형 계산 오류 탐지
- 산출물 누락 탐지

권장 모델 조합:
- Codex critic: 닫힌형 작업, 코드/파일/형식 정합성 검사
- Gemini critic: 출처/내용 커버리지/웹 근거 일치성 검사

출력:
- `iterations/{NN}-critic-codex.md`
- `iterations/{NN}-critic-gemini.md`

이 단계가 가장 중요하다.

현재 Whipper의 실패 패턴은 대부분 여기서 잡힌다:
- Manager가 answer.txt 없이 PASS
- research에서 raw/cross-verification 없이 PASS
- think에서 단일 모델 답을 종합 답으로 오판
- learn에서 학습노트는 만들어졌는데 최종 종료/보고를 놓침

따라서 **최우선 구현 대상은 이 단계**다.

### 3. PASS 확정 후 사용자 답변 직전: `answer compression/polish`

목적:
- 너무 길거나 어색한 최종 답변을 다듬기
- 형식 제약(`한 줄`, `답만`, `세 줄`) 재확인

권장 모델:
- Codex mini 또는 Gemini Flash

주의:
- 사실을 바꾸면 안 된다
- 이 단계는 문장 품질 보정용이지 진실성 검증용이 아니다

출력:
- 별도 파일 없이 `deliverables/answer.txt` rewrite 제안만

효과:
- 사용자 체감 품질은 좋아진다
- 하지만 truth/coverage 측면의 개선 폭은 2단계보다 작다

## 스킬별 권장 배치

### whip

- 1단계 criteria sanity review: 유용
- 2단계 adversarial review: 필수에 가깝다
- 3단계 answer polish: 선택

### whip-think

- 핵심은 2단계다
- think는 이미 멀티 LLM 실행이 들어가므로, Manager 쪽 외부 LLM은 **판정자**로만 쓰는 게 맞다
- 추가 LLM이 답을 하나 더 만드는 구조는 중복 비용이 크고 역할이 흐려진다

### whip-research

- 2단계가 가장 중요하다
- critic은 새 research를 다시 하지 말고 아래만 본다:
  - raw 두 개가 있는가
  - cross-verification이 실제로 있는가
  - 원문 출처 링크가 보고서에 반영됐는가
  - 수치 불일치가 숨겨지지 않았는가

### whip-medical

- 2단계 critic은 도움이 되지만 범위를 좁혀야 한다
- Codex/Gemini는 의료 결론을 새로 내리기보다:
  - 근거 링크 존재 여부
  - 회피 답변 금지 준수 여부
  - profile 반영 여부
  - 위험 신호 누락 여부
  만 확인하는 편이 낫다

### whip-learn

- 2단계 critic은 파일 완성도 체크에 유용하다
- 특히 다음을 잘 잡는다:
  - JSON/md/answer.txt 누락
  - 스크린샷/GIF/Notion 발행 누락
  - 요약 수준으로 축소된 결과

## 구현 순서 제안

### Phase 1

Claude Manager 유지 + Codex critic 1개 추가

- Manager가 초안 평가 작성
- Codex critic이 반례 중심으로 검사
- critic red flag가 있으면 PASS 금지

가장 싸고, 효과 대비 구현 난도가 낮다.

### Phase 2

Gemini critic 추가

- Codex: 결정론/형식/파일/계산
- Gemini: 근거/커버리지/웹 내용 정합성

이 조합이 가장 균형이 좋다.

### Phase 3

원하면 skill별 critic 라우팅

- closed-form / code / format-heavy → Codex 우선
- evidence-heavy / web-heavy → Gemini 우선

## 권장 최종안

1. Manager는 그대로 Claude 유지
2. `Manager 평가 직전`에 외부 critic을 붙인다
3. 첫 critic은 Codex로 시작한다
4. research/medical 품질을 더 올리고 싶으면 Gemini critic을 추가한다
5. Manager 자체 교체는 마지막 단계에서만 검토한다

현재 repo 기준으로 품질 대비 효율이 가장 좋은 위치는:

**Executor 완료 후, Manager PASS/FAIL 직전**
