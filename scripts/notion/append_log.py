#!/usr/bin/env python3
"""Append paragraph blocks to a Notion page body.

Usage:
  python3 append_log.py PAGE_ID "log message"
  echo "multi-line" | python3 append_log.py PAGE_ID -

stdout: OK or FAILED
"""
import sys

from api import notion_patch, to_uuid


def append_log(page_id: str, message: str) -> str:
    """Append a paragraph block to the given Notion page."""
    # Notion block append endpoint
    # page_id can be with or without dashes
    uuid_id = to_uuid(page_id)

    chunks = []
    for i in range(0, len(message), 2000):
        chunks.append(message[i : i + 2000])

    blocks = []
    for chunk in chunks:
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                },
            }
        )

    body = {"children": blocks}
    resp = notion_patch(f"/blocks/{uuid_id}/children", body)

    if resp is None:
        return "FAILED"
    if resp.status_code == 200:
        return "OK"
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    if len(sys.argv) < 3:
        print("Usage: append_log.py PAGE_ID (\"message\" | -)", file=sys.stderr)
        sys.exit(1)

    page_id = sys.argv[1]
    msg_arg = sys.argv[2]

    if msg_arg == "-":
        message = sys.stdin.read()
    else:
        message = msg_arg

    result = append_log(page_id, message.strip())
    print(result, end="")


if __name__ == "__main__":
    main()
