---
description: "Always-on multi-LLM thinking (Claude + Gemini + ChatGPT) with web search"
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

# Whipper Think — Deeper Reasoning

## Step 1: Required API Keys

`whip-think`는 설계상 Claude + Gemini + ChatGPT 3개 LLM 응답이 모두 필요하다.
Gemini/OpenAI 키가 없으면 축소 실행하지 말고 실패해야 한다.

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-think "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
Also read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager-think.md` as a non-optional supplement.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-think.md`.
- Read `${CLAUDE_PLUGIN_ROOT}/prompts/executor-base.md`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/profile.json`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/rules.json`
- Read `.claude/whipper.local.md` to get `task_dir` and `iteration`

Follow the manager workflow exactly:
1. Define success criteria from the command
2. `whip-think`의 필수 성공기준도 반드시 포함한다:
   - Claude/Gemini/ChatGPT 3개 응답 수신
   - `resources/claude-raw.md`, `resources/gemini-raw.md`, `resources/chatgpt-raw.md` 저장
   - `deliverables/종합-분석.md` 에 공통점/차이점/근거 포함
   - `deliverables/answer.txt` 저장
   - `${CLAUDE_PLUGIN_ROOT}/prompts/manager-think.md` 의 PASS 금지 조건 준수
3. Write `README.md` inside the `task_dir`
4. Dispatch the Executor with the actual `task_dir`
5. Evaluate the results against the criteria
6. Record iteration logs
7. Update or delete state via `${CLAUDE_PLUGIN_ROOT}/scripts/core/state.sh`
