# Whipper Plugin Design Spec

## Overview

Claude Code 플러그인. Manager-Executor 구조로 작업을 수행하고, 성공기준을 통과할 때까지 반복한다. 모든 작업은 일감 단위로 기록된다.

## Skills

| Command | Purpose |
|---------|---------|
| `/whip <명령> [--max-iterations N]` | 범용 Manager-Executor 루프 |
| `/whip-think <질문>` | 멀티 LLM thinking (Claude + Gemini + ChatGPT) + 웹검색 → 종합 |
| `/whip-research <주제>` | 멀티 LLM deep research (Gemini + ChatGPT) → 종합 |
| `/whip-medical <증상>` | 의학 디시전 트리. 근거 기반. 회피 답변 금지 |
| `/whip-learn <URL>` | 유튜브 영상/채널 학습 노트 (기존 youtube-summarize 이식) |
| `/whip-cancel` | 실행 중단 |
| `/whip-status` | 현재 상태 + 이력 조회 |

## Plugin Manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "whipper",
  "description": "Manager-Executor loop plugin. Defines success criteria, executes via subagents, evaluates ruthlessly, iterates until passed.",
  "author": {
    "name": "nevermind"
  }
}
```

## Hooks Configuration (`hooks/hooks.json`)

```json
{
  "description": "Whipper stop hook for Manager-Executor loop",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop-hook.sh"
          }
        ]
      }
    ]
  }
}
```

### Stop Hook Behavior (`hooks/stop-hook.sh`)

1. Read `.claude/whipper.local.md` state file
2. Session isolation: compare `session_id` from hook input (`jq -r '.session_id'`) against state file. If different session, `exit 0` (allow exit)
3. If `status: passed` → delete state file, `exit 0` (allow exit)
4. If `max_iterations` reached → delete state file, print warning, `exit 0`
5. If `status: failed` → increment iteration, output:
   ```json
   {
     "decision": "block",
     "reason": "(Manager prompt + 이전 피드백 + executor log)",
     "systemMessage": "🔄 Whipper iteration N/M | skill: {skill}"
   }
   ```

### Loop Mechanism (Manager ↔ Stop Hook)

```
1. /whip 실행 → setup.sh → 상태 파일 생성 (status: running)
2. commands/whip.md가 Manager 역할 프롬프트를 주입
3. Manager가 성공기준 정의 → Executor Agent 디스패치 → 결과 수신
4. Manager가 평가 후 상태 파일에 status: passed 또는 status: failed 기록
5. Manager가 세션 종료 시도 (작업 완료로 판단)
6. Stop hook 발동:
   - status: passed → exit 허용 → 세션 종료
   - status: failed → block → reason에 Manager 프롬프트 + 피드백 재주입 → 다음 iteration
7. 재주입된 프롬프트로 Manager가 다시 Executor 디스패치 → 3번으로 돌아감
```

## Directory Structure

```
whipper/
├── .claude-plugin/plugin.json
├── commands/
│   ├── whip.md
│   ├── whip-think.md
│   ├── whip-research.md
│   ├── whip-medical.md
│   ├── whip-learn.md
│   ├── whip-cancel.md
│   └── whip-status.md
├── hooks/
│   ├── hooks.json
│   └── stop-hook.sh
├── scripts/
│   ├── core/
│   │   ├── setup.sh
│   │   ├── logger.sh
│   │   └── api-keys.sh
│   ├── think/
│   │   ├── gemini-think.py
│   │   └── openai-think.py
│   ├── research/
│   │   ├── gemini-research.py
│   │   └── openai-research.py
│   └── learn/
│       ├── fetch_transcript.py
│       ├── gemini_analyze.py
│       ├── capture_screenshots.py
│       ├── extract_gifs.py
│       ├── upload_images.py
│       ├── generate_study_note.py
│       ├── fetch_channel_videos.py
│       ├── fetch_transcripts.py
│       └── render_notion_md.py
├── prompts/
│   ├── manager.md
│   ├── executor-base.md
│   ├── executor-think.md
│   ├── executor-research.md
│   ├── executor-medical.md
│   └── executor-learn.md
├── config/
│   ├── api-keys.json
│   └── models.json
├── memory/
│   ├── profile.json
│   └── rules.json
└── tests/
    ├── test_core.sh
    ├── test_think.sh
    ├── test_research.sh
    ├── test_medical.sh
    └── test_learn.sh
```

---

## Section 1: Core — Manager-Executor Loop

### Command Frontmatter (`commands/whip.md`)

```yaml
---
description: "Start whipper Manager-Executor loop"
argument-hint: "PROMPT [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "WebSearch",
  "WebFetch"
]
---
```

All other command files follow the same frontmatter pattern with skill-specific `allowed-tools`.

### Manager Prompt (`prompts/manager.md`)

```markdown
# Whipper Manager

너는 Manager다. 명령을 받으면 다음을 수행한다:

## 1단계: 성공기준 정의
- 요청이 성공적으로 완료되었다는 것이 무엇인지 구체적으로 정의
- 각 기준은 객관적으로 검증 가능해야 함
- {task_dir}/README.md에 기록

## 2단계: Executor 디스패치
- Agent 도구로 Executor 서브에이전트 디스패치 (mode: dangerouslySkipPermission)
- Executor 프롬프트에 포함:
  - prompts/executor-base.md 전문
  - 스킬별 프롬프트 (prompts/executor-{skill}.md)
  - memory/profile.json + memory/rules.json
  - 명령 + 성공기준
  - 이전 iteration 피드백 (있으면)

## 3단계: 결과 평가
Executor 결과를 받으면:
- {task_dir}/iterations/{N}-executor-log.md 기록
- 성공기준 각 항목을 PASS/FAIL + 근거로 평가
- 출처 없는 정보가 있는지 검증
- 요청과 다른 것을 해왔는지 검증
- {task_dir}/iterations/{N}-manager-eval.md 기록

## 4단계: 판정
- 모든 기준 PASS → .claude/whipper.local.md에 status: passed 기록 → 세션 종료
- 하나라도 FAIL → status: failed + 구체적 피드백 기록 → 세션 종료 (Stop hook이 block하여 다음 iteration)

## 원칙
- 냉정하고 합리적으로 평가. 기준을 낮추지 않는다
- 통과하지 않은 것을 통과시키지 않는다
- 피드백은 구체적이어야 한다 (무엇이 부족하고, 무엇을 해야 하는지)
```

### Execution Flow

```
1. setup.sh
   → .whipper/tasks/{date}-{slug}/ 폴더 생성
   → .claude/whipper.local.md 상태 파일 생성 (status: running)

2. Manager (메인 세션, commands/whip.md + prompts/manager.md)
   → 명령 분석 → 성공기준 정의 → README.md에 기록
   → Executor를 Agent 서브에이전트로 디스패치 (dangerouslySkipPermission)

3. Executor (서브에이전트)
   → executor-base.md + 스킬별 프롬프트 + memory 로드
   → 작업 수행 (필요시 Worker 서브에이전트 추가 생성, 병렬 가능)
   → 결과 반환

4. Manager 평가
   → iterations/{N}-executor-log.md 기록
   → iterations/{N}-manager-eval.md 기록 (성공기준별 pass/fail + 근거)
   → 통과 → status: passed 기록, deliverables/에 산출물 저장 → 세션 종료
   → 불통과 → status: failed + 피드백 기록 → 세션 종료 시도

5. Stop hook 발동
   → session_id 비교 (다른 세션이면 exit 0)
   → status: passed → 상태 파일 삭제, exit 0 (세션 종료)
   → status: failed → iteration 카운트 증가, block + Manager 프롬프트 재주입
   → max iteration 도달 → 상태 파일 삭제, exit 0 + 사용자에게 보고
```

### State File (`.claude/whipper.local.md`)

```markdown
---
active: true
skill: whip
iteration: 1
max_iterations: 10
session_id: {CLAUDE_CODE_SESSION_ID}
started_at: "2026-03-24T09:00:00Z"
task_dir: ".whipper/tasks/2026-03-24-경쟁사-분석"
status: running
---

경쟁사 분석해줘
```

- `status` values: `running`, `passed`, `failed`
- Stop hook reads `status` to decide block/allow
- Default `max_iterations`: 10, override with `--max-iterations N`, `0` for unlimited

### Manager Evaluation

매 iteration마다 Manager가 판단:
- 성공기준 각 항목 통과 여부 (pass/fail + 근거)
- Executor가 출처 없는 정보를 넣지 않았는지
- 요청한 것과 다른 걸 해오지 않았는지
- `status: passed` 또는 `status: failed` + 피드백을 상태 파일에 기록

### Agent Dispatch Structure

```
Main Session (Manager)
  └─ Executor (Agent, dangerouslySkipPermission, general-purpose)
       ├─ Worker A (Agent — 병렬 작업 1)
       ├─ Worker B (Agent — 병렬 작업 2)
       └─ Worker C (Agent — 병렬 작업 3)
```

Executor는 자기 판단으로 Worker 서브에이전트를 추가 생성 가능.

---

## Section 2: Logging — Task Project Folder

### Folder Structure

```
.whipper/tasks/2026-03-24-경쟁사-분석/
├── README.md              # 명령, 성공기준, 최종 결과 요약
├── iterations/
│   ├── 01-executor-log.md # Executor가 뭘 했는지
│   ├── 01-manager-eval.md # Manager 평가 + 통과 여부
│   ├── 02-executor-log.md
│   └── 02-manager-eval.md
├── deliverables/          # 최종 산출물
└── resources/             # 조사 자료, 스크린샷, 참조 파일, 웹페이지 저장
```

### README.md

```markdown
# 경쟁사 분석

- **명령**: 경쟁사 분석해줘
- **스킬**: /whip
- **시작**: 2026-03-24 09:00
- **종료**: 2026-03-24 09:23
- **iterations**: 3/5
- **결과**: 통과

## 성공기준
- [x] 주요 경쟁사 5곳 이상 식별
- [x] 각 경쟁사별 강점/약점 분석
- [x] 모든 정보에 출처 링크 포함

## 최종 결과 요약
(Manager가 통과 시점에 작성)
```

### executor-log.md

```markdown
# Iteration 01 — Executor Log

## 수행한 작업
1. "SaaS 경쟁사 분석" 키워드로 웹 검색
2. G2, Capterra에서 경쟁 제품 목록 수집
3. 각 제품 공식 사이트 방문하여 기능/가격 확인

## 사용한 도구
- WebSearch: 3회
- /browse: 5회
- Agent (Worker): 2개 병렬 디스패치

## 산출물
- deliverables/경쟁사-분석-보고서.md
- resources/g2-screenshot-01.png
- resources/capterra-data.json
```

### manager-eval.md

```markdown
# Iteration 01 — Manager 평가

## 성공기준 평가
| 기준 | 결과 | 근거 |
|------|------|------|
| 경쟁사 5곳 이상 | FAIL | 3곳만 식별됨 |
| 강점/약점 분석 | PASS | 각 경쟁사별 구체적 분석 포함 |
| 출처 링크 포함 | FAIL | 2곳 출처 누락 |

## 종합: FAIL

## 피드백
- 경쟁사 2곳 추가 필요
- CompanyA, CompanyB 출처 링크 보충 필요
```

### Global Index (`~/.claude/whipper-logs/index.json`)

```json
[
  {
    "id": "2026-03-24-경쟁사-분석",
    "command": "경쟁사 분석해줘",
    "skill": "whip",
    "project": "/Users/nevermind/my-project",
    "path": "/Users/nevermind/my-project/.whipper/tasks/2026-03-24-경쟁사-분석",
    "started_at": "2026-03-24T09:00:00Z",
    "finished_at": "2026-03-24T09:23:00Z",
    "iterations": 3,
    "result": "passed"
  }
]
```

프로젝트별 `.whipper/tasks/`에 실제 파일, `~/.claude/whipper-logs/index.json`에 전체 인덱스.

---

## Section 3: Executor Environment + Base Instructions

### Executor Dispatch

```
Agent(
  prompt: executor-base.md + executor-{skill}.md + memory + 명령 + 성공기준 + 피드백,
  mode: "dangerouslySkipPermission",
  subagent_type: "general-purpose"
)
```

### executor-base.md

```markdown
# Executor 실행 지침

## 절대 원칙
1. 오직 사실만 이야기한다
2. 모든 정보에는 출처 링크를 명시한다. 출처 링크가 없는 정보는 포함하지 않는다
3. 시킨 것을 한다. 불가능하면 불가능하다고 말한다. 되지 않는 다른 것을 대신 해오지 않는다
4. 근거 없는 말은 절대 하지 않는다. 모든 말은 합리적이고 논리적이고 근거가 있어야 한다
5. 명령은 무조건 수행한다. 한두 번 해서 안 된다고 하지 말고 끝까지 한다

## 웹 조사 규칙
- 키워드를 제대로 뽑고 구글, 네이버 등에서 실제로 검색한다
- 실제 웹사이트에 들어가서 정보를 확인한다
- 추가 작업이 필요 없도록 끝까지 조사한다

## 브라우저 사용
- 일반 웹 조사: /browse (gstack headless browser)
- 실제 사이트 조작 필요: mcp__claude-in-chrome__* 도구

## Worker 서브에이전트
- 독립적인 작업이 2개 이상이면 병렬 Worker로 디스패치
- 각 Worker에도 이 실행 지침을 전달

## 산출물 저장
- 최종 산출물 → {task_dir}/deliverables/
- 수집 자료/스크린샷 → {task_dir}/resources/
- 실행 로그 → 결과 반환 시 포함 (Manager가 iterations/에 기록)
```

### Prompt Assembly

Iteration 1:
```
[executor-base.md]
[executor-{skill}.md]
[memory/profile.json]
[memory/rules.json]

## 명령
경쟁사 분석해줘

## 성공기준
1. 주요 경쟁사 5곳 이상 식별
2. ...

## Task 디렉토리
.whipper/tasks/2026-03-24-경쟁사-분석/
```

Iteration 2+ (실패 후):
```
[위와 동일]

## 이전 iteration 피드백
- (Manager 피드백 내용)

## 이전 iteration executor log
- (이전 executor-log.md 내용)
```

---

## Section 4: API Key Management

### Registry (`config/api-keys.json`)

키 값 자체를 저장하지 않고 환경변수 이름을 매핑.

```json
{
  "openai": {
    "env_var": "WHIPPER_OPENAI_API_KEY",
    "fallback": "CALLME_OPENAI_API_KEY",
    "required_by": ["whip-think", "whip-research"],
    "description": "OpenAI API (GPT thinking + deep research)"
  },
  "gemini": {
    "env_var": "WHIPPER_GEMINI_API_KEY",
    "fallback": "GEMINI_API_KEY",
    "required_by": ["whip-think", "whip-research", "whip-learn"],
    "description": "Google Gemini API"
  }
}
```

Note: Claude는 Executor 자체가 Claude이므로 별도 API key 불필요.

### Model Configuration (`config/models.json`)

모델명은 API 변경에 따라 업데이트할 수 있도록 설정 파일로 분리.

```json
{
  "think": {
    "gemini": "gemini-2.5-pro",
    "openai": "o3"
  },
  "research": {
    "gemini": "deep-research-pro-preview-12-2025",
    "openai": "o3-deep-research"
  },
  "learn": {
    "gemini": "gemini-2.5-pro"
  }
}
```

Note: 모델명은 구현 시점에 최신 API 문서를 확인하여 검증할 것.

### `scripts/core/api-keys.sh`

```bash
# 1. WHIPPER_{NAME}_API_KEY 확인
# 2. 없으면 fallback 환경변수 확인
# 3. 둘 다 없으면 에러 + 안내
```

### User Configuration

`settings.json`의 `env`에 추가:
```json
"env": {
  "WHIPPER_OPENAI_API_KEY": "sk-...",
  "WHIPPER_GEMINI_API_KEY": "AIza..."
}
```

설정 안 하면 기존 환경변수(fallback)를 자동 사용. 각 스킬 실행 시 `setup.sh`가 필요한 키 검증, 없으면 안내 후 중단.

---

## Section 5: Skill — whip-think

### Purpose
동일한 질문을 Claude, Gemini, ChatGPT thinking 모델에 동시에 보내고 (웹검색 활성화) 결과를 종합.

### LLM Configuration

| LLM | Model | Web Search | Method |
|-----|-------|-----------|--------|
| Claude | claude-opus-4-6 | WebSearch tool | Executor 자체가 직접 수행 (서브에이전트 불필요) |
| Gemini | config/models.json에서 로드 | google_search tool 활성화 | `scripts/think/gemini-think.py` |
| ChatGPT | config/models.json에서 로드 | web_search_preview tool | `scripts/think/openai-think.py` |

### Execution Flow

```
/whip-think "한국 SaaS 시장에서 버티컬 전략이 유효한가?"

Manager:
  → 성공기준:
    1. 3개 LLM 모두에서 응답 수신
    2. 각 raw 응답이 resources/에 저장됨
    3. 종합 보고서에 각 LLM 의견의 공통점/차이점/근거 포함
    4. 종합 보고서의 모든 주장에 출처(어떤 LLM이 말했는지) 명시

Executor:
  → Claude 파트: Executor 자체가 직접 thinking + WebSearch 수행 → resources/claude-raw.md
  → Worker 2개 병렬 디스패치:
    ├── Worker A: Gemini API (gemini-think.py) → resources/gemini-raw.md
    └── Worker B: ChatGPT API (openai-think.py) → resources/chatgpt-raw.md
  → 3개 결과 종합 → deliverables/종합-분석.md
```

### Output Format

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

---

## Section 6: Skill — whip-research

### Purpose
Gemini, ChatGPT의 deep research 전용 모델을 동시에 활용하여 심층 조사 후 종합.

### LLM Configuration

| LLM | Model | API |
|-----|-------|-----|
| Gemini | `deep-research-pro-preview-12-2025` | Interactions API (`client.interactions.create()`, 비동기 폴링) |
| ChatGPT | `o3-deep-research` | Responses API (`background: true`) |

### Execution Flow

```
/whip-research "한국 B2B SaaS 시장 규모와 성장률 최신 데이터"

Manager:
  → 성공기준:
    1. 2개 LLM research 결과 수신
    2. 각 raw 결과 + 출처 목록이 resources/에 저장
    3. 종합 보고서에 모든 수치의 원본 출처 링크 포함
    4. 출처 간 수치 불일치 시 명시적으로 표기

Executor:
  → Worker 2개 병렬:
    ├── Worker A: Gemini deep research (gemini-research.py)
    └── Worker B: ChatGPT deep research (openai-research.py)
  → Executor 자체가 /browse로 핵심 출처 교차검증
  → resources/:
    ├── resources/gemini-research-raw.md
    ├── resources/chatgpt-research-raw.md
    └── resources/cross-verification.md
  → deliverables/조사-보고서.md
```

### Scripts

**`scripts/research/gemini-research.py`**
- google-generativeai SDK
- Interactions API, `background=True`
- 비동기 폴링으로 완료 대기
- 출력: 응답 텍스트 + grounding_sources (출처 URL 목록)

**`scripts/research/openai-research.py`**
- openai SDK — Responses API
- `model: "o3-deep-research"`, `background: true`
- 출력: 응답 텍스트 + annotations (출처 URL 목록)

### Output Format

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

---

## Section 7: Skill — whip-medical

### Purpose
증상을 입력하면 실제 임상 디시전 트리를 생성. 각 노드에 근거(메타연구/가이드라인) 포함. "병원가봐라" 금지.

### Pre-loaded Data

`memory/profile.json`에서 사용자/반려견 의료 정보 참조. 최초 사용 시 정보 입력받아 저장.

### Execution Flow

```
/whip-medical "강아지가 구토를 3일째 하고 있어. 노란색 거품"

Manager:
  → 성공기준:
    1. 디시전 트리가 완전한 로직 구조 (증상 → 감별진단 → 검사 → 액션)
    2. 각 분기점마다 근거 (논문/가이드라인/메타연구) 출처 포함
    3. 검증되지 않은 민간요법/보조제 미포함
    4. "병원가봐라" 식의 회피 답변 없음 — 구체적 검사명과 로직 제시
    5. profile.json의 기본 정보 반영

Executor:
  → profile.json 로드
  → 웹 검색으로 최신 의학/수의학 가이드라인 및 논문 조사
  → 디시전 트리 작성
```

### executor-medical.md

```markdown
## 금지 사항
- "병원에 가보세요" 식의 회피 답변 금지
- 검증되지 않은 민간요법, 보조식품 추천 금지
- 근거 없는 "~일 수 있습니다" 나열 금지

## 필수 사항
- 모든 감별진단에 근거 논문/가이드라인 출처
- 디시전 트리의 각 분기점에 "왜 이 검사를 하는지" 로직 설명
- 근거 수준 명시 (Level A: 메타분석, B: 임상시험, C: 전문가 의견)
- 실제 병원에서 수행하는 진단 순서를 따름
- profile.json 기본 정보(체중, 기저질환 등) 반영
```

### Output Format

```markdown
# 진단 디시전 트리: {증상}

## 환자 정보
(profile.json에서 로드)

## 1차 감별진단
| 가능성 | 질환 | 근거 |
|--------|------|------|
| 높음 | ... | [출처](URL) |

## 디시전 트리

증상: ...
├── 조건 A?
│   ├── YES → ...
│   │   ├── 검사: ... — 근거: [출처](URL)
│   │   └── 액션: ... — 근거: [출처](URL)
│   └── NO → ...
│       └── ...

## 각 액션의 근거 수준
| 액션 | 근거 수준 | 출처 |
|------|----------|------|
| ... | Level A (메타분석) | [출처](URL) |
```

---

## Section 8: Skill — whip-learn

### Purpose
유튜브 영상/채널의 내용을 학습 가능한 형태로 정리. 기존 youtube-summarize + youtube-to-notion 스킬 이식.

### Scripts (from youtube-summarize/youtube-to-notion)

```
scripts/learn/
├── fetch_transcript.py        # 자막 추출
├── gemini_analyze.py          # Gemini 2.5 Pro 영상 분석
├── capture_screenshots.py     # 키프레임 추출
├── extract_gifs.py            # GIF 클립 생성
├── upload_images.py           # catbox.moe CDN 업로드
├── generate_study_note.py     # 최종 JSON 조립
├── fetch_channel_videos.py    # 채널 영상 목록 수집
├── fetch_transcripts.py       # 배치 자막 추출
└── render_notion_md.py        # Notion 마크다운 변환
```

### Execution Flow — Single Video

```
/whip-learn https://youtube.com/watch?v=abc123

Manager:
  → 성공기준:
    1. 영상의 핵심 내용이 빠짐없이 포함됨 — 요약이 아닌 재구성 수준
    2. 실제 학습에 사용할 수 있는 구조 (개념 정의, 단계별 설명, 맥락)
    3. 영상에서 말한 구체적 표현/비유/예시가 보존됨
    4. 시각적 핵심 장면이 스크린샷/GIF로 캡처됨
    5. 이 노트만 보고 영상을 안 봐도 동일한 수준으로 이해할 수 있음

Executor:
  → 8단계 파이프라인 실행
  → deliverables/에 JSON 학습 노트
  → resources/에 스크린샷, GIF 원본
```

### Execution Flow — Channel (Parallel)

```
/whip-learn https://youtube.com/@channel

Executor:
  → fetch_channel_videos.py로 영상 목록 수집
  → Worker N개 병렬 디스패치 (영상 1개 = Worker 1개)
    ├── Worker 1: 영상 A → 학습 노트 생성
    ├── Worker 2: 영상 B → 학습 노트 생성
    └── Worker N: 영상 N → 학습 노트 생성
  → 전체 완료 후 채널 종합 인덱스 생성
    deliverables/
    ├── index.md
    ├── video-a.json
    ├── video-b.json
    └── ...
```

### Notion Option

```
/whip-learn https://youtube.com/watch?v=abc123 --notion
```

`--notion` 플래그 시 학습 노트 생성 후 render_notion_md.py → Notion MCP로 페이지 생성.

---

## Section 9: Memory

### Structure

```
whipper/memory/
├── profile.json    # key-value (사실 정보)
└── rules.json      # 리스트 (선호/가이드라인)
```

### profile.json

```json
{
  "name": "정승진",
  "company": "...",
  "dog_name": "...",
  "dog_breed": "...",
  "dog_age": 3,
  "dog_weight_kg": 5,
  "dog_conditions": ["..."],
  "allergies": [],
  "medications": []
}
```

### rules.json

```json
[
  "보고서는 항상 한국어로 작성",
  "출처는 APA 스타일",
  "병원가봐라 식의 회피 답변 금지",
  "근거 없는 정보 포함 금지"
]
```

### Behavior

- 모든 Executor 프롬프트 조립 시 profile.json + rules.json 자동 주입
- Manager가 작업 중 새 정보/규칙을 발견하면 자동 추가
- 사용자가 명시적으로 "이거 기억해"라고 하면 적절한 파일에 저장

---

## Section 10: Testing & Evaluation

### Test Flow

```
1. API Key 검증 (사전 조건)
   → api-keys.json의 모든 키가 설정되어 있는지 확인
   → 각 키로 실제 API ping (Gemini, OpenAI 간단한 호출)
   → 하나라도 실패하면 테스트 중단 + 어떤 키가 필요한지 안내

2. 스크립트 단위 테스트
   → setup.sh 폴더 구조 생성 검증
   → api-keys.sh 키 로드/fallback/에러 처리 검증
   → gemini-think.py, openai-think.py API 호출 + 응답 반환 검증
   → learn 스크립트 기존 26+15개 체크

3. E2E 테스트 (실제 API 호출)
   → /whip "대한민국 수도는?" → Manager-Executor 루프 전체 → 로그 생성 확인
   → /whip-think "AI의 미래" → 3개 LLM 실제 응답 → 종합 보고서 → 파일 저장
   → /whip-research "한국 SaaS 시장 규모" → deep research 실제 호출 → 출처 포함
   → /whip-medical "두통이 3일째" → 디시전 트리 + 근거 출처 실제 존재
   → /whip-learn <짧은 유튜브 URL> → 학습 노트 → 내용 완전성

4. 평가 기준
   → 각 E2E 테스트마다 Manager가 실제로 PASS 판정했는지
   → 로그 폴더 구조가 올바른지
   → 글로벌 인덱스에 기록됐는지
```

### Test Scenarios

| Scenario | Expected |
|----------|----------|
| 출처 없는 정보 포함 | FAIL + "출처 누락" 피드백 |
| 요청과 다른 결과 | FAIL + "요청과 불일치" 피드백 |
| 성공기준 전부 충족 | PASS |
| 부분 충족 | FAIL + 미충족 항목 구체적 피드백 |
| API key 누락 | 테스트 시작 전 중단 + 안내 |

---

## Section 11: Skill — whip-cancel

### Command Frontmatter

```yaml
---
description: "Cancel active whipper loop"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)"]
---
```

### Behavior

1. `.claude/whipper.local.md` 존재 여부 확인
2. 없으면 → "활성 whipper 루프 없음" 메시지
3. 있으면 → 상태 파일 삭제 → "whipper 루프 중단됨 (iteration N/M)" 메시지
4. task 폴더는 삭제하지 않음 (기록 보존)
5. 글로벌 인덱스에 `"result": "cancelled"` 기록

---

## Section 12: Skill — whip-status

### Command Frontmatter

```yaml
---
description: "Show whipper status and history"
allowed-tools: ["Read", "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)"]
---
```

### Behavior

1. **현재 실행 중인 루프**: `.claude/whipper.local.md` 읽어서 skill, iteration, max_iterations, 시작 시간, task_dir 표시
2. **현재 프로젝트 이력**: `.whipper/tasks/` 내 폴더 목록 → 각 README.md에서 명령, 결과, iterations 요약
3. **전체 이력** (`--all` 플래그): `~/.claude/whipper-logs/index.json` 읽어서 전체 프로젝트 이력 표시

출력 예시:
```
🔄 Active: "경쟁사 분석" (iteration 2/5, /whip, started 09:00)

📁 Project history:
  2026-03-24 경쟁사-분석     /whip     ✅ passed (3/5)
  2026-03-23 시장-조사       /whip-research  ✅ passed (2/10)
  2026-03-22 두통-진단       /whip-medical   ✅ passed (1/10)
```

---

## Section 13: whip-learn Pipeline Order

8단계 파이프라인 실행 순서:

```
1. fetch_transcript.py     → 자막 추출 (언어 우선순위: 한국어 수동 > 한국어 자동 > 영어 수동 > 영어 자동)
2. gemini_analyze.py       → Gemini 2.5 Pro에 영상 업로드 + 분석 (오디오+비주얼)
3. capture_screenshots.py  → ffmpeg으로 키프레임 6-8장 추출
4. extract_gifs.py         → 핵심 장면 4초 GIF 클립 생성 (480px, 10fps)
5. upload_images.py        → catbox.moe CDN에 스크린샷/GIF 업로드
6. generate_study_note.py  → 분석 결과 + 자막 + 미디어 URL → 최종 JSON 조립
7. (검증)                  → Manager가 성공기준 대비 평가
8. render_notion_md.py     → (--notion 플래그 시) Notion 마크다운 변환 + Notion MCP 발행
```

---

## Section 14: Error Handling

### 상태 파일 손상
- Stop hook에서 YAML 파싱 실패 시 → 상태 파일 삭제, 경고 메시지, exit 0 (ralph-loop 패턴)
- iteration/max_iterations가 숫자가 아닌 경우 → 동일 처리

### Executor Agent 실패
- Agent 호출이 에러를 반환하면 → Manager가 해당 iteration을 FAIL로 기록 + "Executor 실행 실패" 피드백
- 다음 iteration에서 재시도

### API 스크립트 실패
- Python 스크립트가 non-zero exit → Executor가 에러를 포함하여 결과 반환 → Manager가 FAIL 판정

### 병렬 Worker 파일 충돌
- 각 Worker 출력은 고유 prefix 사용 (예: `resources/gemini-raw.md`, `resources/chatgpt-raw.md`)
- Worker는 자기 파일만 쓰고 다른 Worker 파일을 읽지 않음

---

## Design Spec v2 — 2026-03-25 업데이트 (Slack+Notion 통합)

이 세션에서 추가/변경된 기획 의도. 기존 v1 spec과 충돌 시 v2가 우선.

### 핵심 원칙: claude -p에서는 MCP 사용 불가

`claude -p` (headless CLI)는 Slack MCP, Notion MCP에 접근 불가. 따라서:
- **Slack 보고**: 파일 기반 브릿지 (`post.sh` → `slack_messages/` → 데몬 폴링)
- **Notion 기록**: REST API 스크립트 (`scripts/notion/*.py`) + 데몬 자동 업로드
- **Notion 페이지 생성**: 데몬이 `claude -p` 실행 전에 미리 생성
- **Notion 로깅**: 데몬이 PASS/종료 후 `task_dir` 전체를 자동 업로드 (`upload_task.py`)
- **allowed-tools에서 Notion MCP 도구 전부 제거** (모든 스킬)

### Slack 통합

1. **Slack 앱 "Whipper"**: Socket Mode, `@Whipper` 멘션으로 작업 시작
2. **데몬 (`slack_bot.py`)**: Slack 이벤트 수신 → `claude -p` spawn → 브릿지 → 최종 보고
3. **스킬 자동 감지**: YouTube URL → learn, `/think` → think, `/research` → research, `/medical` → medical, 그 외 → whip
4. **Slack 보고 시점**:
   - 🔥 작업 시작 (데몬)
   - 📋 성공기준 + Notion 링크 (Manager → post.sh → 브릿지)
   - 🔧 실행 계획 / 📝 진행 상황 (Executor → post.sh → 브릿지)
   - ✅ 전체 통과 또는 🔄 재시도 필요 (Manager → post.sh → 브릿지)
   - ✅ 작업 완료 (데몬)
5. **스레드 팔로업**: 같은 스레드에 추가 메시지 → 기존 일감 재개

### Notion 통합

1. **Notion REST API 스크립트** (MCP 대신):
   - `create_page.py` — 페이지 생성 → page_id + URL 반환
   - `append_log.py` — 페이지 본문에 텍스트 추가
   - `update_status.py` — Status/Iteration 속성 변경
   - `query_thread.py` — Slack Thread URL로 기존 일감 검색
   - `upload_task.py` — task_dir 전체를 Notion에 업로드 (마크다운 → 네이티브 블록)
2. **자동 업로드**: 데몬이 프로세스 종료 후 `upload_task.py` 실행 → 성공기준, 실행계획, 실행로그, 매니저평가, 결과물 모두 Notion 페이지에 기록
3. **마크다운 → Notion 네이티브 블록**: 테이블 → table 블록, 헤딩 → heading 블록, 리스트 → list 블록, 코드 → code 블록
4. **Status 자동 변경**: PASS → "완료", FAIL/블락 → "블락드"
5. **task_dir 자동 정리**: 업로드 완료 후 데몬이 삭제

### PASS 후 빠른 종료

Manager 5단계:
1. `rm -f .claude/whipper.local.md` (state 파일 삭제 — sed가 아님)
2. 즉시 세션 종료 — Notion/Memory/Publisher 등 추가 작업 금지
3. 데몬이 state 파일 삭제를 감지 → 60초 grace period → force-kill → upload → cleanup

### 기존 일감 재개

데몬이 `query_thread.py`로 Slack Thread URL 매칭하여 기존 Notion 페이지 발견 시:
- 기존 page_id 재사용
- 환경변수로 `claude -p`에 전달 (`WHIPPER_NOTION_PAGE_ID` 등)

### 스케줄러 팔로업

`scheduler.py`가 주기적으로:
- Notion DB에서 "블락드" 또는 오래된 "진행중" 일감 검색
- Slack 스레드에서 완료 마커 확인 → 있으면 Notion 상태 동기화
- 없으면 `run_dispatch()`로 팔로업 실행

### 스킬별 기획 의도 (v2 — 원본 spec과 다른 부분)

#### whip-think: **항상 멀티 LLM**
- v1: "선택적 교차검증" → **v2: 항상 3개 LLM 병렬 (Claude + Gemini + ChatGPT)**
- Claude 파트: Executor 직접 수행 + WebSearch
- Gemini Worker: `gemini-think.py` 병렬 실행
- ChatGPT Worker: `openai-think.py` 병렬 실행
- API 키 없는 LLM만 스킵, 가용한 LLM은 **반드시** 실행
- 종합-분석.md 항상 생성 (3개 LLM 비교표 포함)
- 모든 raw 결과를 resources/에 저장 → Notion에 자동 업로드

#### whip-research: **항상 멀티 LLM Deep Research**
- v1: "짧은 조사는 WebSearch만" → **v2: 항상 Gemini + ChatGPT deep research 병렬**
- Worker A: `gemini-research.py` (Interactions API, 비동기 폴링)
- Worker B: `openai-research.py` (Responses API, background)
- 교차검증: Executor가 WebSearch로 핵심 출처 직접 확인 (항상)
- 출처 불일치 시 명시적 표기
- 조사-보고서.md 항상 생성
- 모든 raw 결과 + cross-verification을 resources/에 저장 → Notion에 자동 업로드

#### whip-learn: YouTube 학습노트
- 기존 v1 파이프라인 유지 (8단계)
- 추가: 비디오 트래킹 DB (`init_video_db.py`, `query_videos.py`, `register_video.py`)
- 추가: 채널 모드에서 중복 체크 후 스킵
- Notion 발행: `render_notion_md.py` → 추적 DB row 페이지에 직접 삽입
- YouTube 임베드: 페이지 최상단에 URL 단독 줄

#### whip-medical: 의료 디시전 트리
- 기존 v1 의도 유지
- 추가: 간단한 질문은 간결하게, 디시전 트리는 명시적 요구 시에만
- 모든 의학 정보에 근거 링크 필수
- profile.json 반영 (반려동물 정보)

### Notion 기록 원칙 (모든 스킬 공통)

**Notion 페이지만 보면 전체 작업을 재현할 수 있어야 한다.**

자동 업로드되는 파일:
- README.md — 성공기준 + 매핑표
- iterations/{N}-execution-plan.md — 실행 계획
- iterations/{N}-executor-log.md — 실행 로그 (수행 작업, 사용 도구, 산출물 목록)
- iterations/{N}-manager-eval.md — 매니저 평가 (기준별 PASS/FAIL + 근거)
- deliverables/* — 최종 결과물 전문
- resources/ 중 .md 파일 — LLM raw 결과, 교차검증, 출처 목록

Notion에서 테이블은 네이티브 table 블록으로 렌더링.
