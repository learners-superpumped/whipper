#!/usr/bin/env python3
"""Update status and/or iteration of a Notion page.

Usage: python3 update_status.py PAGE_ID --status 완료 --iteration 3
stdout: OK or FAILED
"""
import argparse
import sys

from api import notion_patch


def update_status(page_id: str, status: str = None, iteration: int = None) -> str:
    clean_id = page_id.replace("-", "")

    properties = {}
    if status:
        properties["Status"] = {"select": {"name": status}}
    if iteration is not None:
        properties["Iteration"] = {"number": iteration}

    if not properties:
        return "OK"

    body = {"properties": properties}
    resp = notion_patch(f"/pages/{clean_id}", body)

    if resp is None:
        return "FAILED"
    if resp.status_code == 200:
        return "OK"
    else:
        print(f"Notion error: {resp.status_code} {resp.text}", file=sys.stderr)
        return "FAILED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id")
    parser.add_argument("--status", default=None)
    parser.add_argument("--iteration", type=int, default=None)
    args = parser.parse_args()

    result = update_status(args.page_id, args.status, args.iteration)
    print(result, end="")


if __name__ == "__main__":
    main()
