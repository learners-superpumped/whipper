#!/usr/bin/env python3
"""Slack message bridge — polls task_dir/slack_messages/ and posts to Slack."""
import json
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger("whipper-bridge")


class SlackBridge:
    """Watch a directory for .json message files, post them to Slack, delete."""

    def __init__(self, slack_client, poll_interval: float = 5.0):
        self.client = slack_client
        self.poll_interval = poll_interval
        self._watchers: dict[str, threading.Thread] = {}

    def watch(self, task_dir: str, channel: str, thread_ts: str):
        """Start watching {task_dir}/slack_messages/ in background thread."""
        msg_dir = Path(task_dir) / "slack_messages"
        msg_dir.mkdir(parents=True, exist_ok=True)

        key = f"{channel}/{thread_ts}"
        if key in self._watchers and self._watchers[key].is_alive():
            return

        def _poll():
            logger.info(f"Bridge watching: {msg_dir}")
            while True:
                try:
                    for f in sorted(msg_dir.glob("*.json")):
                        try:
                            data = json.loads(f.read_text())
                            self.client.chat_postMessage(
                                channel=data.get("channel", channel),
                                thread_ts=data.get("thread_ts", thread_ts),
                                text=data["text"],
                            )
                            f.unlink()
                            logger.info(f"Bridge posted: {f.name}")
                        except Exception as e:
                            logger.error(f"Bridge post failed: {f.name}: {e}")
                            f.rename(f.with_suffix(".failed"))
                except Exception as e:
                    logger.error(f"Bridge poll error: {e}")
                time.sleep(self.poll_interval)

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
        self._watchers[key] = t
