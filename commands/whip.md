---
description: "Start whipper Manager-Executor loop"
argument-hint: "PROMPT [--max-iterations N]"
allowed-tools: [
  "Agent",
  "Read",
  "Write",
  "Edit",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(test -f *:*)",
  "Bash(sed *:*)",
  "Bash(cat *:*)",
  "Bash(mkdir *:*)",
  "Bash(chmod *:*)",
  "WebSearch",
  "WebFetch",
  "mcp__claude_ai_Notion__notion-create-pages",
  "mcp__claude_ai_Notion__notion-update-page",
  "mcp__claude_ai_Notion__notion-fetch",
  "mcp__claude_ai_Notion__notion-query-database-view",
  "mcp__claude_ai_Notion__notion-search"
]
---

# Whipper — Manager-Executor Loop

## Step 1: Setup

Run the setup script:

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip "$ARGUMENTS"
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
