#!/usr/bin/env python3
"""Register a summarized video in the tracking database.

Usage: python3 register_video.py --title "제목" --channel "채널" --url "URL" \
       --upload-date "2024-01-15" --duration 600 --views 12345 \
       --note-page "https://notion.so/..."

stdout: PAGE_ID or FAILED/NO_DB/NO_TOKEN/DUPLICATE
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_video_database_id, get_headers, notion_post


def check_duplicate(db_id: str, url: str) -> bool:
    """Check if URL already exists in the tracking DB."""
    body = {
        "filter": {
            "property": "URL",
            "url": {"equals": url},
        }
    }
    resp = notion_post(f"/databases/{db_id}/query", body)
    if resp and resp.status_code == 200:
        return len(resp.json().get("results", [])) > 0
    return False


def register_video(title: str, channel: str, url: str, upload_date: str,
                    duration: int, views: int, note_page: str = "") -> str:
    headers = get_headers()
    if not headers:
        return "NO_TOKEN"

    db_id = get_video_database_id()
    if not db_id:
        return "NO_DB"

    if check_duplicate(db_id, url):
        return "DUPLICATE"

    properties = {
        "Name": {"title": [{"text": {"content": title[:100]}}]},
        "Channel": {"rich_text": [{"text": {"content": channel[:100]}}]},
        "URL": {"url": url},
        "Duration": {"number": duration},
        "Views": {"number": views},
    }

    # Parse upload_date to Notion date format (YYYY-MM-DD)
    if upload_date and len(upload_date) >= 8:
        if len(upload_date) == 8 and upload_date.isdigit():
            date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        else:
            date_str = upload_date[:10]
        properties["Upload Date"] = {"date": {"start": date_str}}

    if note_page:
        properties["Note Page"] = {"url": note_page}

    body = {"parent": {"database_id": db_id}, "properties": properties}

    resp = notion_post("/pages", body)
    if resp is None:
        return "NO_TOKEN"

    if resp.status_code == 200:
        page_id = resp.json()["id"].replace("-", "")
        return page_id
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--upload-date", default="")
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--views", type=int, default=0)
    parser.add_argument("--note-page", default="")
    args = parser.parse_args()

    result = register_video(
        args.title, args.channel, args.url,
        args.upload_date, args.duration, args.views, args.note_page
    )
    print(result, end="")


if __name__ == "__main__":
    main()
