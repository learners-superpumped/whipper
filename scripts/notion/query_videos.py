#!/usr/bin/env python3
"""Query video tracking DB to find already-summarized videos.

Usage:
  python3 query_videos.py --urls URL1 URL2 ...
  python3 query_videos.py --channel "채널명"
  python3 query_videos.py --all

stdout: JSON array of {url, title, channel, note_page} for matching entries
        or [] if none found
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import get_video_database_id, notion_post


def _parse_page(page: dict) -> dict:
    """Extract video info from a Notion page object."""
    props = page.get("properties", {})
    url_prop = props.get("URL", {}).get("url", "")
    title_prop = props.get("Name", {}).get("title", [])
    title = title_prop[0]["text"]["content"] if title_prop else ""
    channel_prop = props.get("Channel", {}).get("rich_text", [])
    channel = channel_prop[0]["text"]["content"] if channel_prop else ""
    note_prop = props.get("Note Page", {}).get("url", "")

    return {
        "url": url_prop or "",
        "title": title,
        "channel": channel,
        "note_page": note_prop or "",
    }


def _query_db(db_id: str, body: dict) -> list[dict]:
    """Run a paginated query against the tracking DB."""
    results = []
    has_more = True
    start_cursor = None

    while has_more:
        req = {**body, "page_size": 100}
        if start_cursor:
            req["start_cursor"] = start_cursor

        resp = notion_post(f"/databases/{db_id}/query", req)
        if resp is None or resp.status_code != 200:
            break

        data = resp.json()
        for page in data.get("results", []):
            results.append(_parse_page(page))

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def query_all_videos() -> list[dict]:
    db_id = get_video_database_id()
    if not db_id:
        return []
    return _query_db(db_id, {})


def query_by_urls(urls: list[str]) -> list[dict]:
    db_id = get_video_database_id()
    if not db_id:
        return []

    if len(urls) == 1:
        filter_body = {
            "filter": {"property": "URL", "url": {"equals": urls[0]}}
        }
    else:
        filter_body = {
            "filter": {
                "or": [
                    {"property": "URL", "url": {"equals": url}}
                    for url in urls
                ]
            }
        }

    return _query_db(db_id, filter_body)


def query_by_channel(channel: str) -> list[dict]:
    db_id = get_video_database_id()
    if not db_id:
        return []

    filter_body = {
        "filter": {
            "property": "Channel",
            "rich_text": {"contains": channel},
        }
    }
    return _query_db(db_id, filter_body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", nargs="+", help="YouTube URLs to check")
    parser.add_argument("--channel", help="Channel name to filter by")
    parser.add_argument("--all", action="store_true", help="List all tracked videos")
    args = parser.parse_args()

    if args.urls:
        results = query_by_urls(args.urls)
    elif args.channel:
        results = query_by_channel(args.channel)
    else:
        results = query_all_videos()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
