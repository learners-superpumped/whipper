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
"${CLAUDE_PLUGIN_ROOT}/scripts/core/setup.sh" --skill whip-think "$ARGUMENTS"
```

## Step 3: Execute as Manager

Read and follow `${CLAUDE_PLUGIN_ROOT}/prompts/manager.md`.
The Executor prompt must include `${CLAUDE_PLUGIN_ROOT}/prompts/executor-think.md`.
