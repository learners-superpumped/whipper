#!/usr/bin/env python3
"""Create a Whipper project page in Notion DB.

Usage: python3 create_page.py --name "Task" --skill whip --slack-url "https://..." --content "initial body"
stdout: PAGE_ID URL (space-separated) or FAILED/NO_DB/NO_TOKEN
"""
import argparse
import sys

from api import get_database_id, get_headers, notion_post


def create_page(name: str, skill: str, slack_url: str = "", content: str = "") -> str:
    headers = get_headers()
    if not headers:
        return "NO_TOKEN"

    db_id = get_database_id()
    if not db_id:
        return "NO_DB"

    properties = {
        "Name": {"title": [{"text": {"content": name[:100]}}]},
        "Status": {"select": {"name": "진행중"}},
        "Skill": {"select": {"name": skill}},
        "Iteration": {"number": 1},
    }
    if slack_url:
        properties["Slack Thread"] = {"url": slack_url}

    body = {"parent": {"database_id": db_id}, "properties": properties}

    # Add initial content as children blocks
    if content:
        body["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content[:2000]}}]
                },
            }
        ]

    resp = notion_post("/pages", body)
    if resp is None:
        return "NO_TOKEN"

    if resp.status_code == 200:
        data = resp.json()
        page_id = data["id"].replace("-", "")
        url = data.get("url", "")
        return f"{page_id} {url}"
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--skill", default="whip")
    parser.add_argument("--slack-url", default="")
    parser.add_argument("--content", default="")
    args = parser.parse_args()

    result = create_page(args.name, args.skill, args.slack_url, args.content)
    print(result, end="")


if __name__ == "__main__":
    main()
