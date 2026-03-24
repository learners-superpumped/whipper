---
description: "Cancel active whipper loop"
allowed-tools: [
  "Bash(test -f .claude/whipper.local.md:*)",
  "Bash(rm .claude/whipper.local.md)",
  "Read(.claude/whipper.local.md)",
  "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)"
]
---

# Cancel Whipper

1. Check if `.claude/whipper.local.md` exists: `test -f .claude/whipper.local.md && echo "EXISTS" || echo "NOT_FOUND"`

2. **If NOT_FOUND**: Say "활성 whipper 루프 없음"

3. **If EXISTS**:
   - Read `.claude/whipper.local.md` to get iteration, max_iterations, skill, task_dir
   - Remove the file: `rm .claude/whipper.local.md`
   - Update global index via logger.sh: set result to "cancelled"
   - Report: "Whipper 루프 중단됨 (iteration N/M, skill: X)"
   - Task folder is preserved for record keeping.
