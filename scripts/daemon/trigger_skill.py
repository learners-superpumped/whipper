#!/usr/bin/env python3
"""Post a Slack test message and run a whipper skill in that thread."""
import argparse
import sys
from pathlib import Path

from slack_bolt import App

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.slack.bridge import SlackBridge
from slack_bot import detect_skill
from scripts.daemon.dispatch import load_slack_config, run_dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True)
    parser.add_argument("--skill", default="")
    parser.add_argument("prompt")
    args = parser.parse_args()

    cfg = load_slack_config()
    app = App(token=cfg["bot_token"])
    bridge = SlackBridge(app.client)
    skill = args.skill or detect_skill(args.prompt)

    top = app.client.chat_postMessage(
        channel=args.channel,
        text=f"🧪 {skill} test\n{args.prompt}",
    )
    thread_ts = top["ts"]
    run_dispatch(
        app.client,
        bridge,
        f"[Slack thread: {args.channel}/{thread_ts}] {args.prompt}",
        skill,
        args.channel,
        thread_ts,
    )
    print(thread_ts)


if __name__ == "__main__":
    main()
