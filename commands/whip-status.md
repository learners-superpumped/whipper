---
description: "Show whipper status and history"
argument-hint: "[--all]"
allowed-tools: [
  "Read",
  "Bash(ls *:*)",
  "Bash(cat *:*)",
  "Bash(test *:*)",
  "Bash(find *:*)",
  "Bash(head *:*)",
  "Bash(jq *:*)",
  "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)"
]
---

# Whipper Status

## Current Loop
Check `.claude/whipper.local.md`:
- If exists: show skill, iteration/max_iterations, started_at, task_id, notion_page_id
- If not: "No active whipper loop"

## Project History (Notion 우선)
1. Read config/notion.json에서 database_id 확인
2. **database_id가 있으면**: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/list_projects.py" --limit 10` 로 최근 프로젝트 조회
3. **database_id가 없으면**: `~/.claude/whipper-logs/index.json`에서 읽기 (하위 호환)

Format:
```
🔄 Active: "{command}" (iteration N/M, /skill, started HH:MM)

📋 Recent projects:
  Name              Status    Skill          Created
  경쟁사 분석        완료      whip           2026-03-24
  리조트 검색        진행중    whip           2026-03-25
```

## All Projects (--all flag)
If $ARGUMENTS contains "--all", read `~/.claude/whipper-logs/index.json` and list all entries across projects.
