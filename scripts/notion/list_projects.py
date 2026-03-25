#!/usr/bin/env python3
"""List recent Whipper projects from the Notion database.

Usage:
  python3 list_projects.py --limit 10
  python3 list_projects.py --limit 50 --format json
"""
import argparse
import json
import sys

from api import get_database_id, notion_post


def _title(page: dict) -> str:
    title_prop = page.get("properties", {}).get("Name", {}).get("title", [])
    return "".join(part.get("plain_text", "") for part in title_prop)


def _select_name(page: dict, prop: str) -> str:
    select = (page.get("properties", {}).get(prop, {}).get("select")) or {}
    return select.get("name", "")


def _url(page: dict, prop: str) -> str:
    return page.get("properties", {}).get(prop, {}).get("url") or ""


def list_projects(limit: int = 10) -> list[dict]:
    db_id = get_database_id()
    if not db_id:
        return []

    body = {
        "page_size": max(1, limit),
        "sorts": [{"property": "Created", "direction": "descending"}],
    }
    response = notion_post(f"/databases/{db_id}/query", body)
    if response is None or response.status_code != 200:
        return []

    rows = []
    for page in response.json().get("results", []):
        rows.append(
            {
                "page_id": page["id"].replace("-", ""),
                "name": _title(page),
                "status": _select_name(page, "Status"),
                "skill": _select_name(page, "Skill"),
                "created": page.get("created_time", ""),
                "slack_thread": _url(page, "Slack Thread"),
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--format", choices=["tsv", "json"], default="tsv")
    args = parser.parse_args()

    rows = list_projects(args.limit)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False))
        return

    for row in rows:
        print(
            "\t".join(
                [
                    row["page_id"],
                    row["name"],
                    row["status"],
                    row["skill"],
                    row["created"],
                    row["slack_thread"],
                ]
            )
        )


if __name__ == "__main__":
    main()
