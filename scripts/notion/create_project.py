#!/usr/bin/env python3
"""Create a Whipper project page in Notion DB.

Usage: python3 create_project.py --name "Task Name" --skill whip --slack-url "https://..."
Returns: page_id on stdout
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("", end="")
    sys.exit(1)


def get_notion_token():
    for var in ["WHIPPER_NOTION_TOKEN", "NOTION_TOKEN"]:
        token = os.environ.get(var)
        if token:
            return token
    return None


def get_database_id():
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "notion.json"
    if not config_path.exists():
        return None
    cfg = json.loads(config_path.read_text())
    return cfg.get("database_id")


def create_page(name: str, skill: str, slack_url: str = "") -> str:
    token = get_notion_token()
    db_id = get_database_id()
    if not token or not db_id:
        return ""

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    properties = {
        "Name": {"title": [{"text": {"content": name[:100]}}]},
        "Status": {"select": {"name": "진행중"}},
        "Skill": {"select": {"name": skill}},
        "Iteration": {"number": 1},
    }
    if slack_url:
        properties["Slack Thread"] = {"url": slack_url}

    body = {"parent": {"database_id": db_id}, "properties": properties}

    resp = requests.post("https://api.notion.com/v1/pages", headers=headers, json=body)
    if resp.status_code == 200:
        page_id = resp.json()["id"].replace("-", "")
        return page_id
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--skill", default="whip")
    parser.add_argument("--slack-url", default="")
    args = parser.parse_args()

    page_id = create_page(args.name, args.skill, args.slack_url)
    print(page_id, end="")


if __name__ == "__main__":
    main()
