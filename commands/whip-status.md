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
