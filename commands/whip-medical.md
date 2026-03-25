---
description: "Evidence-based medical guidance"
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

# Whipper Medical — Evidence-Based Guidance

## Step 1: Setup

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-medical "$ARGUMENTS"
```

## Step 2: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-medical.md`.
Ensure profile.json medical data is loaded into the Executor prompt.
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
