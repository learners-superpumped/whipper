---
description: "YouTube video/channel study notes (v3 - topic-based, Gemini analysis)"
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

# Whipper Learn — YouTube Summary / Study Notes

## Step 1: Gemini 우선, transcript 폴백 허용

원본 `youtube-summarize` 스킬처럼 Gemini 분석이 기본 경로다.
다만 Gemini 키가 없거나 분석이 실패하면 transcript 기반 파이프라인으로 계속 진행해야 한다.

## Step 2: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-learn "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-learn.md`.
- Read `${CLAUDE_PLUGIN_ROOT}/prompts/executor-base.md`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/profile.json`
- Read `${CLAUDE_PLUGIN_ROOT}/memory/rules.json`
- Read `.claude/whipper.local.md` to get `task_dir` and `iteration`

Follow the manager workflow exactly:
1. Define success criteria from the command
2. Write `README.md` inside the `task_dir`
3. Dispatch the Executor with the actual `task_dir`
4. Evaluate the results against the criteria
5. Record iteration logs
6. Update or delete state via `${CLAUDE_PLUGIN_ROOT}/scripts/core/state.sh`
