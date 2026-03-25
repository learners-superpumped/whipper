#!/usr/bin/env python3
"""Build a Slack thread URL from runtime config."""

from __future__ import annotations

import sys

from scripts.core.runtime_config import build_slack_thread_url, load_slack_config


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: slack_url.py CHANNEL THREAD_TS", file=sys.stderr)
        return 1

    cfg = load_slack_config()
    try:
        url = build_slack_thread_url(
            cfg.get("workspace_domain", ""),
            sys.argv[1],
            sys.argv[2],
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(url, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
