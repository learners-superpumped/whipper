#!/usr/bin/env python3
"""Run one scheduler follow-up cycle from the command line."""
import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

import sys

sys.path.insert(0, str(ROOT_DIR / "scripts" / "daemon"))

from scheduler import load_scheduler_config, run_scheduled_followups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_scheduler_config()
    if args.dry_run:
        config["todo_check"]["dry_run"] = True

    result = run_scheduled_followups(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
