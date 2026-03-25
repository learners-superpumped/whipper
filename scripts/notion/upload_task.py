#!/usr/bin/env python3
"""Upload entire task_dir contents to a Notion page.
Usage: python3 upload_task.py PAGE_ID TASK_DIR [--iteration N]
  --iteration N: only upload iteration N files (for FAIL mid-loop)
  without --iteration: upload everything (for final PASS)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import notion_patch


def text_to_blocks(text, max_len=2000):
    blocks = []
    for i in range(0, len(text), max_len):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[i:i+max_len]}}]
            },
        })
    return blocks


def heading_block(text, level=2):
    h_type = f"heading_{level}"
    return {
        "object": "block",
        "type": h_type,
        h_type: {
            "rich_text": [{"type": "text", "text": {"content": text[:100]}}]
        },
    }


def divider_block():
    return {"object": "block", "type": "divider", "divider": {}}


def upload_file(page_id, heading, content):
    """Append a heading + content blocks to the page."""
    if not content.strip():
        return
    blocks = [heading_block(heading), *text_to_blocks(content), divider_block()]
    # Notion API limits 100 blocks per request
    for i in range(0, len(blocks), 100):
        notion_patch(f"blocks/{page_id}/children", {"children": blocks[i:i+100]})


def upload_all(page_id, task_dir):
    """Upload everything in task_dir to the Notion page."""
    td = Path(task_dir)

    # 1. README.md (성공기준)
    readme = td / "README.md"
    if readme.exists():
        upload_file(page_id, "📋 성공기준", readme.read_text())

    # 2. iterations/ (실행계획, 실행로그, 매니저평가)
    iters_dir = td / "iterations"
    if iters_dir.exists():
        for f in sorted(iters_dir.glob("*.md")):
            label = f.stem  # e.g. "01-execution-plan"
            upload_file(page_id, f"📝 {label}", f.read_text())

    # 3. deliverables/ (결과물)
    deliv_dir = td / "deliverables"
    if deliv_dir.exists():
        for f in sorted(deliv_dir.glob("*")):
            if f.is_file():
                try:
                    content = f.read_text()
                except UnicodeDecodeError:
                    content = f"(바이너리 파일: {f.name}, {f.stat().st_size} bytes)"
                upload_file(page_id, f"📦 결과물: {f.name}", content)


def upload_iteration(page_id, task_dir, iteration):
    """Upload only a specific iteration's files."""
    td = Path(task_dir) / "iterations"
    prefix = f"{iteration:02d}-"
    for f in sorted(td.glob(f"{prefix}*.md")):
        upload_file(page_id, f"📝 Iteration {iteration}: {f.stem}", f.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id")
    parser.add_argument("task_dir")
    parser.add_argument("--iteration", type=int, default=None)
    parser.add_argument("--status", default=None, help="Update page Status property")
    args = parser.parse_args()

    if args.iteration:
        upload_iteration(args.page_id, args.task_dir, args.iteration)
    else:
        upload_all(args.page_id, args.task_dir)

    if args.status:
        notion_patch(f"pages/{args.page_id}", {
            "properties": {"Status": {"select": {"name": args.status}}}
        })

    print("OK", end="")


if __name__ == "__main__":
    main()
