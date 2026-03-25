---
description: "Always-on multi-LLM deep research (Gemini + ChatGPT) with source cross-checks"
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

## Step 1: Required API Keys

`whip-research`는 설계상 Gemini deep research + ChatGPT deep research 2개 결과가 모두 필요하다.
Gemini/OpenAI 키가 없으면 fallback 축소 실행하지 말고 실패해야 한다.

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-research "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
Also read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager-research.md` as a non-optional supplement.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-research.md`.
- Read `${CLAUDE_PLUGIN_ROOT}/prompts/executor-base.md`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/profile.json`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/rules.json`
- Read `.claude/whipper.local.md` to get `task_dir` and `iteration`

Follow the manager workflow exactly:
1. Define success criteria from the command
2. `whip-research`의 필수 성공기준도 반드시 포함한다:
   - Gemini/ChatGPT deep research 2개 raw 결과 수신
   - `resources/gemini-research-raw.md`, `resources/chatgpt-research-raw.md`, `resources/cross-verification.md` 저장
   - `deliverables/조사-보고서.md` 에 원본 출처 링크 포함
   - `deliverables/answer.txt` 저장
   - `${CLAUDE_PLUGIN_ROOT}/prompts/manager-research.md` 의 PASS 금지 조건 준수
3. Write `README.md` inside the `task_dir`
4. Dispatch the Executor with the actual `task_dir`
5. Evaluate the results against the criteria
6. Record iteration logs
7. Update or delete state via `${CLAUDE_PLUGIN_ROOT}/scripts/core/state.sh`
