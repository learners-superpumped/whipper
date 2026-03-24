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
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-learn "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-learn.md`.
