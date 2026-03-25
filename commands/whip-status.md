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
1. Notion 설정은 `config/notion.json` 또는 환경변수(`WHIPPER_NOTION_DATABASE_ID`, `NOTION_DATABASE_ID`)로 들어올 수 있다고 가정한다
2. 먼저 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notion/list_projects.py" --limit 10` 로 최근 프로젝트 조회를 시도한다
3. 위 명령이 설정 부족으로 실패하면 `~/.claude/whipper-logs/index.json`에서 읽기 (하위 호환)

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
