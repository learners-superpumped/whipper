#!/usr/bin/env python3
"""Upload entire task_dir contents to a Notion page.
Usage: python3 upload_task.py PAGE_ID TASK_DIR [--iteration N] [--status STATUS]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import notion_patch, to_uuid


def rich_text(text):
    """Create a rich_text element, truncated to 2000 chars."""
    return [{"type": "text", "text": {"content": text[:2000]}}]


def md_to_blocks(text):
    """Convert markdown text to Notion blocks (headings, tables, bullets, code, paragraphs)."""
    blocks = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Heading
        if line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": rich_text(line[2:].strip())}})
            i += 1
            continue
        if line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": rich_text(line[3:].strip())}})
            i += 1
            continue
        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": rich_text(line[4:].strip())}})
            i += 1
            continue

        # Table (markdown pipe table)
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            # Parse header
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip header + separator

            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1

            # Build Notion table block
            width = len(headers)
            table_rows = []

            # Header row
            table_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [[{"type": "text", "text": {"content": h[:2000]}}] for h in headers]
                }
            })

            # Data rows
            for row in rows:
                # Pad or truncate to match header width
                padded = (row + [""] * width)[:width]
                table_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [[{"type": "text", "text": {"content": c[:2000]}}] for c in padded]
                    }
                })

            blocks.append({
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": width,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": table_rows,
                }
            })
            continue

        # Bulleted list
        if line.startswith("- ") or line.startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich_text(line[2:].strip())}})
            i += 1
            continue

        # Numbered list
        m = re.match(r"^(\d+)\.\s+(.+)", line)
        if m:
            blocks.append({"object": "block", "type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": rich_text(m.group(2).strip())}})
            i += 1
            continue

        # Code block
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append({"object": "block", "type": "code",
                           "code": {"rich_text": rich_text("\n".join(code_lines)),
                                    "language": lang or "plain text"}})
            continue

        # Empty line → skip
        if not line.strip():
            i += 1
            continue

        # Default: paragraph
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": rich_text(line)}})
        i += 1

    return blocks


def heading_block(text, level=2):
    h_type = f"heading_{level}"
    return {"object": "block", "type": h_type, h_type: {"rich_text": rich_text(text[:100])}}


def divider_block():
    return {"object": "block", "type": "divider", "divider": {}}


def upload_file(page_id, heading, content):
    """Append a heading + parsed markdown blocks to the page."""
    if not content.strip():
        return
    page_id = to_uuid(page_id)
    blocks = [heading_block(heading), *md_to_blocks(content), divider_block()]
    for i in range(0, len(blocks), 100):
        notion_patch(f"blocks/{page_id}/children", {"children": blocks[i:i + 100]})


def upload_all(page_id, task_dir):
    """Upload everything in task_dir to the Notion page."""
    td = Path(task_dir)

    readme = td / "README.md"
    if readme.exists():
        upload_file(page_id, "📋 성공기준", readme.read_text())

    iters_dir = td / "iterations"
    if iters_dir.exists():
        for f in sorted(iters_dir.glob("*.md")):
            upload_file(page_id, f"📝 {f.stem}", f.read_text())

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
    parser.add_argument("--status", default=None)
    args = parser.parse_args()

    if args.iteration:
        upload_iteration(args.page_id, args.task_dir, args.iteration)
    else:
        upload_all(args.page_id, args.task_dir)

    if args.status:
        notion_patch(f"pages/{to_uuid(args.page_id)}", {
            "properties": {"Status": {"select": {"name": args.status}}}
        })

    print("OK", end="")


if __name__ == "__main__":
    main()
