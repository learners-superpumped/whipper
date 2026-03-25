#!/usr/bin/env python3
"""Create the YouTube video tracking database in Notion.

Usage: python3 init_video_db.py --parent-page-id PAGE_ID
stdout: DATABASE_ID or FAILED/NO_TOKEN/ALREADY_EXISTS
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_headers, notion_post, load_config, CONFIG_PATH


def create_video_db(parent_page_id: str) -> str:
    headers = get_headers()
    if not headers:
        return "NO_TOKEN"

    cfg = load_config()
    if cfg.get("video_database_id"):
        return "ALREADY_EXISTS"

    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": "YouTube 학습노트 통합"}}],
        "properties": {
            "Name": {"title": {}},
            "Channel": {"rich_text": {}},
            "URL": {"url": {}},
            "Upload Date": {"date": {}},
            "Duration": {"number": {"format": "number"}},
            "Views": {"number": {"format": "number_with_commas"}},
            "Note Page": {"url": {}},
        },
    }

    resp = notion_post("/databases", body)
    if resp is None:
        return "NO_TOKEN"

    if resp.status_code == 200:
        db_id = resp.json()["id"].replace("-", "")
        cfg["video_database_id"] = db_id
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        return db_id
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-page-id", required=True,
                        help="Notion page ID under which to create the tracking database")
    args = parser.parse_args()
    result = create_video_db(args.parent_page_id)
    print(result, end="")


if __name__ == "__main__":
    main()
