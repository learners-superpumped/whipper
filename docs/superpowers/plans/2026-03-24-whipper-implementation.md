# Whipper Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin with Manager-Executor loop that evaluates work against success criteria and iterates until passed.

**Architecture:** Stop hook intercepts session exit, re-injects Manager prompt on failure. Manager dispatches Executor as Agent subagent (dangerouslySkipPermission). Each skill has its own command file + prompt + optional scripts.

**Tech Stack:** Bash (hooks/setup), Python (API scripts), Markdown (commands/prompts), JSON (config/memory)

**Spec:** `docs/superpowers/specs/2026-03-24-whipper-design.md`

---

### Task 1: Plugin Scaffold + Manifest

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `config/api-keys.json`
- Create: `config/models.json`
- Create: `memory/profile.json`
- Create: `memory/rules.json`

- [ ] **Step 1: Create plugin manifest**

```json
// .claude-plugin/plugin.json
{
  "name": "whipper",
  "description": "Manager-Executor loop plugin. Defines success criteria, executes via subagents, evaluates ruthlessly, iterates until passed.",
  "author": {
    "name": "nevermind"
  }
}
```

- [ ] **Step 2: Create config files**

```json
// config/api-keys.json
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

```json
// config/models.json
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

- [ ] **Step 3: Create memory files**

```json
// memory/profile.json
{}
```

```json
// memory/rules.json
[]
```

- [ ] **Step 4: Verify directory structure**

Run: `find . -type f | sort`
Expected: All 5 files present.

---

### Task 2: Core Scripts — setup.sh, api-keys.sh, logger.sh

**Files:**
- Create: `scripts/core/setup.sh`
- Create: `scripts/core/api-keys.sh`
- Create: `scripts/core/logger.sh`

- [ ] **Step 1: Write setup.sh**

This script initializes a whipper task: creates task folder, state file, global index entry.

```bash
#!/bin/bash
# Whipper Setup Script — creates state file + task folder
set -euo pipefail

# Parse arguments (same pattern as ralph-loop)
PROMPT_PARTS=()
MAX_ITERATIONS=10
SKILL="whip"

while [[ $# -gt 0 ]]; do
  case $1 in
    --max-iterations)
      [[ -z "${2:-}" ]] && echo "❌ --max-iterations requires a number" >&2 && exit 1
      [[ ! "$2" =~ ^[0-9]+$ ]] && echo "❌ --max-iterations must be integer, got: $2" >&2 && exit 1
      MAX_ITERATIONS="$2"; shift 2 ;;
    --skill)
      SKILL="$2"; shift 2 ;;
    --notion)
      # Pass through for whip-learn
      PROMPT_PARTS+=("--notion"); shift ;;
    *)
      PROMPT_PARTS+=("$1"); shift ;;
  esac
done

PROMPT="${PROMPT_PARTS[*]:-}"
[[ -z "$PROMPT" ]] && echo "❌ No prompt provided" >&2 && exit 1

# Generate task slug from prompt (first 30 chars, sanitized)
SLUG=$(echo "$PROMPT" | head -c 30 | sed 's/[^a-zA-Z0-9가-힣]/-/g' | sed 's/--*/-/g' | sed 's/-$//')
DATE=$(date +%Y-%m-%d)
TASK_DIR=".whipper/tasks/${DATE}-${SLUG}"

# Create task folder structure
mkdir -p "$TASK_DIR/iterations" "$TASK_DIR/deliverables" "$TASK_DIR/resources"

# Create state file
mkdir -p .claude
cat > .claude/whipper.local.md <<EOF
---
active: true
skill: $SKILL
iteration: 1
max_iterations: $MAX_ITERATIONS
session_id: ${CLAUDE_CODE_SESSION_ID:-}
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
task_dir: "$TASK_DIR"
status: running
---

$PROMPT
EOF

# Create global index directory
GLOBAL_INDEX="$HOME/.claude/whipper-logs/index.json"
mkdir -p "$(dirname "$GLOBAL_INDEX")"
[[ ! -f "$GLOBAL_INDEX" ]] && echo "[]" > "$GLOBAL_INDEX"

# Append entry to global index
TEMP=$(mktemp)
jq --arg id "${DATE}-${SLUG}" \
   --arg cmd "$PROMPT" \
   --arg skill "$SKILL" \
   --arg project "$PWD" \
   --arg path "$PWD/$TASK_DIR" \
   --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '. += [{id: $id, command: $cmd, skill: $skill, project: $project, path: $path, started_at: $started, finished_at: null, iterations: 0, result: "running"}]' \
   "$GLOBAL_INDEX" > "$TEMP" && mv "$TEMP" "$GLOBAL_INDEX"

# Output
cat <<EOF
🔥 Whipper activated!

Skill: $SKILL
Task: $TASK_DIR
Iteration: 1
Max iterations: $(if [[ $MAX_ITERATIONS -gt 0 ]]; then echo $MAX_ITERATIONS; else echo "unlimited"; fi)

$PROMPT
EOF
```

- [ ] **Step 2: Write api-keys.sh**

```bash
#!/bin/bash
# API Key resolver — source this file, then call get_api_key "openai"
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
API_KEYS_CONFIG="$PLUGIN_ROOT/config/api-keys.json"

get_api_key() {
  local name="$1"
  local env_var fallback value

  env_var=$(jq -r --arg n "$name" '.[$n].env_var // ""' "$API_KEYS_CONFIG")
  fallback=$(jq -r --arg n "$name" '.[$n].fallback // ""' "$API_KEYS_CONFIG")

  # Try primary
  value="${!env_var:-}"
  [[ -n "$value" ]] && echo "$value" && return 0

  # Try fallback
  if [[ -n "$fallback" ]]; then
    value="${!fallback:-}"
    [[ -n "$value" ]] && echo "$value" && return 0
  fi

  echo "❌ API key '$name' not found. Set $env_var or $fallback in settings.json env." >&2
  return 1
}

check_required_keys() {
  local skill="$1"
  local missing=()

  for name in $(jq -r 'to_entries[] | select(.value.required_by | index($skill)) | .key' --arg skill "$skill" "$API_KEYS_CONFIG"); do
    if ! get_api_key "$name" > /dev/null 2>&1; then
      missing+=("$name")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "❌ Missing API keys for $skill: ${missing[*]}" >&2
    echo "   Set them in ~/.claude/settings.json env section." >&2
    return 1
  fi
}
```

- [ ] **Step 3: Write logger.sh**

```bash
#!/bin/bash
# Logger utility — writes to task iteration files and updates global index
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Update global index entry on completion
update_global_index() {
  local task_id="$1"
  local result="$2"
  local iterations="$3"
  local global_index="$HOME/.claude/whipper-logs/index.json"

  [[ ! -f "$global_index" ]] && return 0

  local temp=$(mktemp)
  jq --arg id "$task_id" \
     --arg result "$result" \
     --argjson iters "$iterations" \
     --arg finished "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     'map(if .id == $id then . + {result: $result, iterations: $iters, finished_at: $finished} else . end)' \
     "$global_index" > "$temp" && mv "$temp" "$global_index"
}
```

- [ ] **Step 4: Make scripts executable**

Run: `chmod +x scripts/core/setup.sh scripts/core/api-keys.sh scripts/core/logger.sh`

- [ ] **Step 5: Test setup.sh locally**

Run: `CLAUDE_CODE_SESSION_ID=test123 bash scripts/core/setup.sh --skill whip --max-iterations 5 "테스트 명령"`
Expected: `.claude/whipper.local.md` created, `.whipper/tasks/` folder created, global index updated.

Run: `cat .claude/whipper.local.md`
Expected: YAML frontmatter with skill: whip, iteration: 1, max_iterations: 5, status: running

- [ ] **Step 6: Cleanup test artifacts**

Run: `rm -rf .claude/whipper.local.md .whipper/tasks/`

---

### Task 3: Stop Hook

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/stop-hook.sh`

- [ ] **Step 1: Write hooks.json**

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

- [ ] **Step 2: Write stop-hook.sh**

Modeled after ralph-loop's stop-hook.sh. Key differences: reads `status` field, re-injects manager prompt with feedback.

```bash
#!/bin/bash
# Whipper Stop Hook — blocks exit on status: failed, allows on status: passed
set -euo pipefail

HOOK_INPUT=$(cat)
STATE_FILE=".claude/whipper.local.md"

# No state file → allow exit
[[ ! -f "$STATE_FILE" ]] && exit 0

# Parse YAML frontmatter
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$STATE_FILE")
ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
SKILL=$(echo "$FRONTMATTER" | grep '^skill:' | sed 's/skill: *//')
STATUS=$(echo "$FRONTMATTER" | grep '^status:' | sed 's/status: *//')
TASK_DIR=$(echo "$FRONTMATTER" | grep '^task_dir:' | sed 's/task_dir: *//' | sed 's/^"\(.*\)"$/\1/')

# Session isolation
STATE_SESSION=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' || true)
HOOK_SESSION=$(echo "$HOOK_INPUT" | jq -r '.session_id // ""')
if [[ -n "$STATE_SESSION" ]] && [[ "$STATE_SESSION" != "$HOOK_SESSION" ]]; then
  exit 0
fi

# Validate numeric fields
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]] || [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "⚠️  Whipper: State file corrupted. Stopping." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Status: passed → allow exit, update global index
if [[ "$STATUS" == "passed" ]]; then
  # Source logger and update global index
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  source "$PLUGIN_ROOT/scripts/core/logger.sh"
  TASK_ID=$(basename "$TASK_DIR")
  update_global_index "$TASK_ID" "passed" "$ITERATION"
  rm "$STATE_FILE"
  exit 0
fi

# Max iterations reached → allow exit with warning
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  echo "🛑 Whipper: Max iterations ($MAX_ITERATIONS) reached."
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  source "$PLUGIN_ROOT/scripts/core/logger.sh"
  TASK_ID=$(basename "$TASK_DIR")
  update_global_index "$TASK_ID" "max_iterations" "$ITERATION"
  rm "$STATE_FILE"
  exit 0
fi

# Status: failed or running → block and re-inject
NEXT_ITERATION=$((ITERATION + 1))

# Extract prompt (everything after closing ---)
PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$STATE_FILE")
if [[ -z "$PROMPT_TEXT" ]]; then
  echo "⚠️  Whipper: No prompt in state file. Stopping." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Read latest manager eval for feedback (if exists)
EVAL_FILE="$TASK_DIR/iterations/$(printf '%02d' "$ITERATION")-manager-eval.md"
FEEDBACK=""
if [[ -f "$EVAL_FILE" ]]; then
  FEEDBACK=$(cat "$EVAL_FILE")
fi

# Read latest executor log
LOG_FILE="$TASK_DIR/iterations/$(printf '%02d' "$ITERATION")-executor-log.md"
EXEC_LOG=""
if [[ -f "$LOG_FILE" ]]; then
  EXEC_LOG=$(cat "$LOG_FILE")
fi

# Update iteration in state file
TEMP_FILE="${STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE" | \
  sed "s/^status: .*/status: running/" > "$TEMP_FILE"
mv "$TEMP_FILE" "$STATE_FILE"

# Build re-injection reason
REASON="$PROMPT_TEXT"
if [[ -n "$FEEDBACK" ]]; then
  REASON="$REASON

## 이전 iteration Manager 평가
$FEEDBACK"
fi
if [[ -n "$EXEC_LOG" ]]; then
  REASON="$REASON

## 이전 iteration Executor 로그
$EXEC_LOG"
fi

SYSTEM_MSG="🔄 Whipper iteration $NEXT_ITERATION/$MAX_ITERATIONS | skill: $SKILL"

jq -n \
  --arg prompt "$REASON" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
```

- [ ] **Step 3: Make executable**

Run: `chmod +x hooks/stop-hook.sh`

---

### Task 4: Prompts — Manager + Executor Base

**Files:**
- Create: `prompts/manager.md`
- Create: `prompts/executor-base.md`

- [ ] **Step 1: Write manager.md**

```markdown
# Whipper Manager

너는 Manager다. 명령을 받으면 다음을 수행한다:

## 1단계: 성공기준 정의
- 요청이 성공적으로 완료되었다는 것이 무엇인지 구체적으로 정의
- 각 기준은 객관적으로 검증 가능해야 함
- {task_dir}/README.md에 기록

## 2단계: Executor 디스패치
- Agent 도구로 Executor 서브에이전트 디스패치 (mode: bypassPermissions)
- Executor 프롬프트에 포함할 내용:
  - prompts/executor-base.md 전문을 Read로 읽어서 포함
  - 해당 스킬의 prompts/executor-{skill}.md를 Read로 읽어서 포함
  - memory/profile.json 내용
  - memory/rules.json 내용
  - 명령 + 성공기준
  - task_dir 경로
  - 이전 iteration 피드백 (있으면 — Stop hook이 재주입한 내용에서 확인)

## 3단계: 결과 평가
Executor 결과를 받으면:
- Executor의 실행 내용을 {task_dir}/iterations/{N}-executor-log.md에 기록
- 성공기준 각 항목을 PASS/FAIL + 근거로 평가
- 출처 없는 정보가 있는지 검증
- 요청과 다른 것을 해왔는지 검증
- {task_dir}/iterations/{N}-manager-eval.md에 평가 기록

## 4단계: 판정
- 모든 기준 PASS:
  1. .claude/whipper.local.md에 status: passed로 수정 (sed 사용)
  2. {task_dir}/README.md 업데이트 (종료 시간, 결과 요약)
  3. 세션 종료

- 하나라도 FAIL:
  1. .claude/whipper.local.md에 status: failed로 수정 (sed 사용)
  2. 세션 종료 (Stop hook이 block하여 다음 iteration으로 재주입)

## 원칙
- 냉정하고 합리적으로 평가. 기준을 낮추지 않는다
- 통과하지 않은 것을 통과시키지 않는다
- 피드백은 구체적이어야 한다 (무엇이 부족하고, 무엇을 해야 하는지)
- Executor가 출처 없는 정보를 가져오면 무조건 FAIL
- Executor가 시킨 것과 다른 것을 해오면 무조건 FAIL
```

- [ ] **Step 2: Write executor-base.md**

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
- WebSearch, WebFetch 도구를 활용한다

## 브라우저 사용
- 일반 웹 조사: WebSearch + WebFetch
- 실제 사이트 조작 필요: mcp__claude-in-chrome__* 도구

## Worker 서브에이전트
- 독립적인 작업이 2개 이상이면 병렬 Worker로 디스패치 (Agent 도구)
- 각 Worker에도 이 실행 지침의 절대 원칙을 전달

## 산출물 저장
- 최종 산출물 → {task_dir}/deliverables/
- 수집 자료/스크린샷/참조 파일 → {task_dir}/resources/

## 결과 반환
작업 완료 시 반드시 다음을 포함하여 반환:
1. 수행한 작업 목록
2. 사용한 도구 목록
3. 생성/저장한 파일 목록
4. 성공기준 각 항목에 대한 자체 평가
```

---

### Task 5: Command — /whip (Core Loop)

**Files:**
- Create: `commands/whip.md`

- [ ] **Step 1: Write whip.md**

```markdown
---
description: "Start whipper Manager-Executor loop"
argument-hint: "PROMPT [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test -f *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "Bash(chmod *:*)",
  "WebSearch",
  "WebFetch"
]
---

# Whipper — Manager-Executor Loop

## Step 1: Setup

Run the setup script:

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip $ARGUMENTS
```

## Step 2: Load Manager Instructions

Read the manager prompt and execute it:
- Read `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`
- Read `${CLAUDE_PLUGIN_ROOT}/prompts/executor-base.md` (to include in Executor dispatch)
- Read `${CLAUDE_PLUGIN_ROOT}/memory/profile.json`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/rules.json`
- Read `.claude/whipper.local.md` to get task_dir and iteration

## Step 3: Execute as Manager

Follow the manager.md instructions exactly:
1. Define success criteria for the given command
2. Write README.md in the task directory
3. Dispatch Executor as Agent subagent (mode: bypassPermissions, subagent_type: general-purpose)
4. Evaluate results against success criteria
5. Record iteration logs
6. Update state file status (passed/failed)

The Stop hook will handle looping on failure.
```

---

### Task 6: Commands — /whip-cancel, /whip-status

**Files:**
- Create: `commands/whip-cancel.md`
- Create: `commands/whip-status.md`

- [ ] **Step 1: Write whip-cancel.md**

```markdown
---
description: "Cancel active whipper loop"
allowed-tools: [
  "Bash(test -f .claude/whipper.local.md:*)",
  "Bash(rm .claude/whipper.local.md)",
  "Read(.claude/whipper.local.md)",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)"
]
---

# Cancel Whipper

1. Check if `.claude/whipper.local.md` exists: `test -f .claude/whipper.local.md && echo "EXISTS" || echo "NOT_FOUND"`

2. **If NOT_FOUND**: Say "활성 whipper 루프 없음"

3. **If EXISTS**:
   - Read `.claude/whipper.local.md` to get iteration, max_iterations, skill, task_dir
   - Remove the file: `rm .claude/whipper.local.md`
   - Update global index via logger.sh: set result to "cancelled"
   - Report: "Whipper 루프 중단됨 (iteration N/M, skill: X)"
   - Task folder is preserved for record keeping.
```

- [ ] **Step 2: Write whip-status.md**

```markdown
---
description: "Show whipper status and history"
argument-hint: "[--all]"
allowed-tools: [
  "Read",
  "Bash(ls *:*)",
  "Bash(cat *:*)",
  "Bash(test *:*)",
  "Bash(find *:*)",
  "Bash(head *:*)"
]
---

# Whipper Status

## Current Loop
Check `.claude/whipper.local.md`:
- If exists: show skill, iteration/max_iterations, started_at, task_dir
- If not: "No active whipper loop"

## Project History
List `.whipper/tasks/` directories. For each, read the first 10 lines of README.md to extract command, result, iterations.

Format:
```
🔄 Active: "{command}" (iteration N/M, /skill, started HH:MM)

📁 Project history:
  YYYY-MM-DD task-slug    /skill    ✅ passed (N/M)
  YYYY-MM-DD task-slug    /skill    ❌ failed (N/M)
```

## All Projects (--all flag)
If $ARGUMENTS contains "--all", also read `~/.claude/whipper-logs/index.json` and list all entries across projects.
```

---

### Task 7: Skill Prompts — executor-think, executor-research, executor-medical, executor-learn

**Files:**
- Create: `prompts/executor-think.md`
- Create: `prompts/executor-research.md`
- Create: `prompts/executor-medical.md`
- Create: `prompts/executor-learn.md`

- [ ] **Step 1: Write executor-think.md**

```markdown
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
```

- [ ] **Step 2: Write executor-research.md**

```markdown
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
```

- [ ] **Step 3: Write executor-medical.md**

```markdown
# Executor — whip-medical

의학 디시전 트리 생성. 실제 임상 로직 기반.

## 사전 데이터
memory/profile.json에서 환자/반려견 정보를 로드하여 반영한다.

## 금지 사항
- "병원에 가보세요" 식의 회피 답변 금지
- 검증되지 않은 민간요법, 보조식품 추천 금지
- 근거 없는 "~일 수 있습니다" 나열 금지

## 필수 사항
- 모든 감별진단에 근거 논문/가이드라인 출처 (URL 포함)
- 디시전 트리의 각 분기점에 "왜 이 검사를 하는지" 로직 설명
- 근거 수준 명시 (Level A: 메타분석/체계적 리뷰, B: 임상시험, C: 전문가 의견/가이드라인)
- 실제 병원에서 수행하는 진단 순서를 따름
- profile.json 기본 정보(체중, 나이, 기저질환 등) 반영
- WebSearch로 최신 가이드라인/논문 검색하여 근거 확보

## 출력 형식

```markdown
# 진단 디시전 트리: {증상}

## 환자 정보
(profile.json 기반)

## 1차 감별진단
| 가능성 | 질환 | 근거 |

## 디시전 트리
(트리 형태로 조건 → 검사 → 액션, 각각 근거 포함)

## 각 액션의 근거 수준
| 액션 | 근거 수준 | 출처 |
```

저장: {task_dir}/deliverables/진단-디시전-트리.md
```

- [ ] **Step 4: Write executor-learn.md**

```markdown
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
```

---

### Task 8: Command Files — /whip-think, /whip-research, /whip-medical, /whip-learn

**Files:**
- Create: `commands/whip-think.md`
- Create: `commands/whip-research.md`
- Create: `commands/whip-medical.md`
- Create: `commands/whip-learn.md`

- [ ] **Step 1: Write whip-think.md**

```markdown
---
description: "Multi-LLM thinking with web search — Claude + Gemini + ChatGPT"
argument-hint: "QUESTION [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 *:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "WebSearch",
  "WebFetch"
]
---

# Whipper Think — Multi-LLM Thinking

## Step 1: Check API Keys

```!
source "${CLAUDE_PLUGIN_ROOT}/scripts/core/api-keys.sh" && check_required_keys "whip-think"
```

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-think $ARGUMENTS
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-think.md`.
```

- [ ] **Step 2: Write whip-research.md**

```markdown
---
description: "Deep research via Gemini + ChatGPT research APIs"
argument-hint: "TOPIC [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 *:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "WebSearch",
  "WebFetch"
]
---

# Whipper Research — Deep Research

## Step 1: Check API Keys

```!
source "${CLAUDE_PLUGIN_ROOT}/scripts/core/api-keys.sh" && check_required_keys "whip-research"
```

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-research $ARGUMENTS
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-research.md`.
```

- [ ] **Step 3: Write whip-medical.md**

```markdown
---
description: "Medical decision tree with evidence-based diagnosis"
argument-hint: "SYMPTOMS [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "WebSearch",
  "WebFetch"
]
---

# Whipper Medical — Evidence-Based Diagnosis

## Step 1: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-medical $ARGUMENTS
```

## Step 2: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-medical.md`.
Ensure profile.json medical data is loaded into the Executor prompt.
```

- [ ] **Step 4: Write whip-learn.md**

```markdown
---
description: "YouTube video/channel study notes"
argument-hint: "URL [--max-iterations N] [--notion]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 *:*)",
  "Bash(test *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "Bash(chmod *:*)",
  "WebSearch",
  "WebFetch"
]
---

# Whipper Learn — YouTube Study Notes

## Step 1: Check API Keys

```!
source "${CLAUDE_PLUGIN_ROOT}/scripts/core/api-keys.sh" && check_required_keys "whip-learn"
```

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-learn $ARGUMENTS
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-learn.md`.
```

---

### Task 9: Python Scripts — think/

**Files:**
- Create: `scripts/think/gemini-think.py`
- Create: `scripts/think/openai-think.py`

- [ ] **Step 1: Write gemini-think.py**

```python
#!/usr/bin/env python3
"""Gemini thinking with web search. Reads prompt from stdin or arg, prints response to stdout."""
import sys
import os
import json

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("WHIPPER_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Load model from config
    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("think", {}).get("gemini", "gemini-2.5-pro")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_budget=8192),
        ),
    )

    # Extract text and sources
    output_parts = []
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            output_parts.append(part.text)

    result = "\n".join(output_parts)

    # Extract grounding sources if available
    grounding = getattr(response.candidates[0], "grounding_metadata", None)
    if grounding and hasattr(grounding, "grounding_chunks"):
        result += "\n\n## Sources\n"
        for chunk in grounding.grounding_chunks:
            if hasattr(chunk, "web") and chunk.web:
                result += f"- [{chunk.web.title}]({chunk.web.uri})\n"

    print(result)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write openai-think.py**

```python
#!/usr/bin/env python3
"""OpenAI thinking with web search. Reads prompt from stdin or arg, prints response to stdout."""
import sys
import os
import json

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("WHIPPER_OPENAI_API_KEY") or os.environ.get("CALLME_OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("think", {}).get("openai", "o3")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model_name,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
    )

    # Extract text and annotations
    result_parts = []
    sources = []
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    result_parts.append(content.text)
                    if hasattr(content, "annotations"):
                        for ann in content.annotations:
                            if ann.type == "url_citation":
                                sources.append(f"- [{ann.title}]({ann.url})")

    result = "\n".join(result_parts)
    if sources:
        result += "\n\n## Sources\n" + "\n".join(sources)

    print(result)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Make executable**

Run: `chmod +x scripts/think/gemini-think.py scripts/think/openai-think.py`

---

### Task 10: Python Scripts — research/

**Files:**
- Create: `scripts/research/gemini-research.py`
- Create: `scripts/research/openai-research.py`

- [ ] **Step 1: Write gemini-research.py**

```python
#!/usr/bin/env python3
"""Gemini deep research via Interactions API. Async polling."""
import sys
import os
import json
import time

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("WHIPPER_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("research", {}).get("gemini", "deep-research-pro-preview-12-2025")

    from google import genai

    client = genai.Client(api_key=api_key)

    # Start deep research interaction
    interaction = client.interactions.create(
        agent=model_name,
        user_message=prompt,
        background=True,
        store=True,
    )

    # Poll until complete (max 30 min)
    max_wait = 1800
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.interactions.get(interaction.id)
        if status.status == "COMPLETED":
            break
        if status.status == "FAILED":
            print(f"Error: Research failed — {status.error}", file=sys.stderr)
            sys.exit(1)
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    # Extract result
    result = status.response.text if hasattr(status.response, "text") else str(status.response)

    # Extract sources
    if hasattr(status, "grounding_metadata") and status.grounding_metadata:
        result += "\n\n## Sources\n"
        for chunk in status.grounding_metadata.grounding_chunks:
            if hasattr(chunk, "web") and chunk.web:
                result += f"- [{chunk.web.title}]({chunk.web.uri})\n"

    print(result)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write openai-research.py**

```python
#!/usr/bin/env python3
"""OpenAI deep research via Responses API with background mode."""
import sys
import os
import json
import time

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("WHIPPER_OPENAI_API_KEY") or os.environ.get("CALLME_OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("research", {}).get("openai", "o3-deep-research")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    # Start background deep research
    response = client.responses.create(
        model=model_name,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
        background=True,
    )

    # Poll until complete (max 30 min)
    max_wait = 1800
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.responses.retrieve(response.id)
        if status.status == "completed":
            break
        if status.status == "failed":
            print(f"Error: Research failed", file=sys.stderr)
            sys.exit(1)
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    # Extract result
    result_parts = []
    sources = []
    for item in status.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    result_parts.append(content.text)
                    if hasattr(content, "annotations"):
                        for ann in content.annotations:
                            if ann.type == "url_citation":
                                sources.append(f"- [{ann.title}]({ann.url})")

    result = "\n".join(result_parts)
    if sources:
        result += "\n\n## Sources\n" + "\n".join(sources)

    print(result)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Make executable**

Run: `chmod +x scripts/research/gemini-research.py scripts/research/openai-research.py`

---

### Task 11: Copy learn/ scripts from youtube-summarize

**Files:**
- Copy from: `~/.claude/skills/youtube-summarize/scripts/*`
- Copy from: `~/.claude/skills/youtube-to-notion/scripts/fetch_channel_videos.py`
- Copy from: `~/.claude/skills/youtube-to-notion/scripts/fetch_transcripts.py`
- Copy from: `~/.claude/skills/youtube-to-notion/scripts/render_notion_md.py`
- To: `scripts/learn/`

- [ ] **Step 1: Copy youtube-summarize scripts**

Run:
```bash
mkdir -p scripts/learn
cp ~/.claude/skills/youtube-summarize/scripts/fetch_transcript.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/gemini_analyze.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/capture_screenshots.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/extract_gifs.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/upload_images.py scripts/learn/
cp ~/.claude/skills/youtube-summarize/scripts/generate_study_note.py scripts/learn/
```

- [ ] **Step 2: Copy youtube-to-notion scripts**

Run:
```bash
cp ~/.claude/skills/youtube-to-notion/scripts/fetch_channel_videos.py scripts/learn/
cp ~/.claude/skills/youtube-to-notion/scripts/fetch_transcripts.py scripts/learn/
cp ~/.claude/skills/youtube-to-notion/scripts/render_notion_md.py scripts/learn/
```

- [ ] **Step 3: Copy test files**

Run:
```bash
mkdir -p tests
cp ~/.claude/skills/tests/test_youtube_summarize.py tests/test_learn_summarize.py
cp ~/.claude/skills/tests/test_youtube_to_notion.py tests/test_learn_notion.py
```

- [ ] **Step 4: Make executable**

Run: `chmod +x scripts/learn/*.py`

- [ ] **Step 5: Verify all files present**

Run: `ls -la scripts/learn/`
Expected: 9 Python files.

---

### Task 12: Test Scripts

**Files:**
- Create: `tests/test_core.sh`
- Create: `tests/test_api_keys.sh`

- [ ] **Step 1: Write test_core.sh**

```bash
#!/bin/bash
# Core integration test — setup, state file, logging, stop hook
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

check() {
  local name="$1" cond="$2"
  if eval "$cond"; then
    echo "  ✅ $name"
    ((PASS++))
  else
    echo "  ❌ $name"
    ((FAIL++))
  fi
}

echo "=== Test: setup.sh ==="

# Clean up
rm -rf .claude/whipper.local.md .whipper/tasks/

# Run setup
export CLAUDE_CODE_SESSION_ID="test-session-123"
bash "$PLUGIN_ROOT/scripts/core/setup.sh" --skill whip --max-iterations 5 "테스트 명령어" > /dev/null

check "State file created" "[[ -f .claude/whipper.local.md ]]"
check "Task folder created" "[[ -d .whipper/tasks/ ]]"
check "Task has iterations dir" "ls .whipper/tasks/*/iterations/ > /dev/null 2>&1"
check "Task has deliverables dir" "ls .whipper/tasks/*/deliverables/ > /dev/null 2>&1"
check "Task has resources dir" "ls .whipper/tasks/*/resources/ > /dev/null 2>&1"
check "State file has iteration: 1" "grep -q 'iteration: 1' .claude/whipper.local.md"
check "State file has max_iterations: 5" "grep -q 'max_iterations: 5' .claude/whipper.local.md"
check "State file has skill: whip" "grep -q 'skill: whip' .claude/whipper.local.md"
check "State file has status: running" "grep -q 'status: running' .claude/whipper.local.md"
check "State file has session_id" "grep -q 'session_id: test-session-123' .claude/whipper.local.md"
check "State file has prompt" "grep -q '테스트 명령어' .claude/whipper.local.md"
check "Global index updated" "jq -e '.[-1].skill == \"whip\"' ~/.claude/whipper-logs/index.json > /dev/null"

echo ""
echo "=== Test: api-keys.sh ==="

source "$PLUGIN_ROOT/scripts/core/api-keys.sh"

export WHIPPER_GEMINI_API_KEY="test-key-123"
check "get_api_key primary" "[[ \$(get_api_key gemini) == 'test-key-123' ]]"

unset WHIPPER_GEMINI_API_KEY
export GEMINI_API_KEY="fallback-key-456"
check "get_api_key fallback" "[[ \$(get_api_key gemini) == 'fallback-key-456' ]]"

unset GEMINI_API_KEY
check "get_api_key missing" "! get_api_key gemini 2>/dev/null"

echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

# Cleanup
rm -rf .claude/whipper.local.md .whipper/tasks/

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
```

- [ ] **Step 2: Write test_api_keys.sh**

```bash
#!/bin/bash
# API key ping test — verifies keys actually work
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$PLUGIN_ROOT/scripts/core/api-keys.sh"

echo "=== API Key Verification ==="

# Gemini
GEMINI_KEY=$(get_api_key gemini 2>/dev/null || true)
if [[ -n "$GEMINI_KEY" ]]; then
  echo -n "  Gemini: "
  RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_KEY")
  [[ "$RESP" == "200" ]] && echo "✅ OK" || echo "❌ HTTP $RESP"
else
  echo "  Gemini: ⚠️  Not configured"
fi

# OpenAI
OPENAI_KEY=$(get_api_key openai 2>/dev/null || true)
if [[ -n "$OPENAI_KEY" ]]; then
  echo -n "  OpenAI: "
  RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $OPENAI_KEY" \
    "https://api.openai.com/v1/models")
  [[ "$RESP" == "200" ]] && echo "✅ OK" || echo "❌ HTTP $RESP"
else
  echo "  OpenAI: ⚠️  Not configured"
fi
```

- [ ] **Step 3: Make executable**

Run: `chmod +x tests/test_core.sh tests/test_api_keys.sh`

- [ ] **Step 4: Run test_core.sh**

Run: `cd /Users/nevermind/.claude/plugins/marketplaces/whipper && bash tests/test_core.sh`
Expected: All checks pass.

---

### Task 13: Verify Full Plugin Structure

- [ ] **Step 1: Verify all files exist**

Run: `find . -type f | grep -v '.git' | sort`

Expected:
```
./.claude-plugin/plugin.json
./commands/whip-cancel.md
./commands/whip-learn.md
./commands/whip-medical.md
./commands/whip-research.md
./commands/whip-status.md
./commands/whip-think.md
./commands/whip.md
./config/api-keys.json
./config/models.json
./docs/superpowers/plans/2026-03-24-whipper-implementation.md
./docs/superpowers/specs/2026-03-24-whipper-design.md
./hooks/hooks.json
./hooks/stop-hook.sh
./memory/profile.json
./memory/rules.json
./prompts/executor-base.md
./prompts/executor-learn.md
./prompts/executor-medical.md
./prompts/executor-research.md
./prompts/executor-think.md
./prompts/manager.md
./scripts/core/api-keys.sh
./scripts/core/logger.sh
./scripts/core/setup.sh
./scripts/learn/*.py (9 files)
./scripts/research/gemini-research.py
./scripts/research/openai-research.py
./scripts/think/gemini-think.py
./scripts/think/openai-think.py
./tests/test_api_keys.sh
./tests/test_core.sh
./tests/test_learn_notion.py
./tests/test_learn_summarize.py
```

- [ ] **Step 2: Run unit tests**

Run: `bash tests/test_core.sh`
Expected: All pass.

- [ ] **Step 3: Run API key verification**

Run: `bash tests/test_api_keys.sh`
Expected: At least Gemini shows OK (key exists in settings.json).
