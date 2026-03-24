---
description: "Cancel active whipper loop"
allowed-tools: [
  "Bash(test -f .claude/whipper.local.md:*)",
  "Bash(rm .claude/whipper.local.md)",
  "Read(.claude/whipper.local.md)",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "mcp__claude_ai_Notion__notion-update-page"
]
---

# Cancel Whipper

1. Check if `.claude/whipper.local.md` exists: `test -f .claude/whipper.local.md && echo "EXISTS" || echo "NOT_FOUND"`

2. **If NOT_FOUND**: Say "활성 whipper 루프 없음"

3. **If EXISTS**:
   - Read `.claude/whipper.local.md` to get iteration, max_iterations, skill, task_id, notion_page_id
   - Remove the file: `rm .claude/whipper.local.md`
   - Update global index via logger.sh: set result to "cancelled"
   - **notion_page_id가 비어있지 않으면**: notion-update-page로 Status를 "드랍"으로 변경
   - Report: "Whipper 루프 중단됨 (iteration N/M, skill: X)"
