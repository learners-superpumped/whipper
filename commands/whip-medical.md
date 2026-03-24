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
