#!/usr/bin/env python3
"""Publish a markdown file into an existing Notion page body.

Usage:
  python3 publish_markdown.py PAGE_ID PATH/TO/file.md [--youtube-url URL]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import notion_patch, to_uuid
from upload_task import md_to_blocks


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
        },
    }


def publish_markdown(page_id: str, markdown_path: str, youtube_url: str = "") -> str:
    path = Path(markdown_path)
    if not path.exists():
        return "MISSING_FILE"

    markdown = path.read_text()
    blocks = []
    if youtube_url:
        blocks.append(_paragraph_block(youtube_url))
    blocks.extend(md_to_blocks(markdown))

    uuid_id = to_uuid(page_id)
    for i in range(0, len(blocks), 100):
        response = notion_patch(f"blocks/{uuid_id}/children", {"children": blocks[i : i + 100]})
        if response is None or response.status_code != 200:
            return "FAILED"
    return "OK"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id")
    parser.add_argument("markdown_path")
    parser.add_argument("--youtube-url", default="")
    args = parser.parse_args()

    result = publish_markdown(args.page_id, args.markdown_path, args.youtube_url)
    print(result, end="")
    if result != "OK":
        sys.exit(1)


if __name__ == "__main__":
    main()
