#!/usr/bin/env python3
"""Query Notion DB for a page by Slack thread URL.

Usage: python3 query_thread.py "https://learnerscompany.slack.com/archives/C0AHV8FCH6V/p1234"
stdout: PAGE_ID\tNAME\tITERATION\tSTATUS  or  NOT_FOUND
"""
import sys

from api import get_database_id, notion_post


def query_thread(slack_url: str) -> str:
    db_id = get_database_id()
    if not db_id:
        return "NOT_FOUND"

    body = {
        "filter": {
            "property": "Slack Thread",
            "url": {"equals": slack_url},
        }
    }

    resp = notion_post(f"/databases/{db_id}/query", body)
    if resp is None:
        return "NOT_FOUND"

    if resp.status_code != 200:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "NOT_FOUND"

    results = resp.json().get("results", [])
    if not results:
        return "NOT_FOUND"

    page = results[0]
    page_id = page["id"].replace("-", "")
    props = page.get("properties", {})

    # Extract name from title property
    name_prop = props.get("Name", {}).get("title", [])
    name = name_prop[0]["text"]["content"] if name_prop else ""

    # Extract iteration
    iteration = props.get("Iteration", {}).get("number", 0) or 0

    # Extract status
    status_prop = props.get("Status", {}).get("select")
    status = status_prop["name"] if status_prop else ""

    return f"{page_id}\t{name}\t{iteration}\t{status}"


def main():
    if len(sys.argv) < 2:
        print("Usage: query_thread.py SLACK_URL", file=sys.stderr)
        sys.exit(1)

    result = query_thread(sys.argv[1])
    print(result, end="")


if __name__ == "__main__":
    main()
