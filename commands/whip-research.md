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
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-research "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-research.md`.
