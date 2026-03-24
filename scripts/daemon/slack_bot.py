#!/usr/bin/env python3
"""Whipper Slack Bot — 얇은 릴레이.

역할: Slack 이벤트 수신 → claude CLI spawn → stdout을 스레드에 회신.
Notion/프로젝트 로직 = 0. 모든 지능은 Claude 세션 안에서.
"""
import os
import sys
import json
import re
import subprocess
import threading
import logging
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("whipper-daemon")

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_slack_config() -> dict:
    config_path = CONFIG_DIR / "slack.json"
    if not config_path.exists():
        logger.error("config/slack.json not found. Copy slack.json.example and fill in tokens.")
        sys.exit(1)
    return json.loads(config_path.read_text())


def detect_skill(text: str) -> str:
    """메시지에서 스킬 판단. 불확실하면 whip(기본)."""
    t = text.lower()
    if "youtube.com" in t or "youtu.be" in t:
        return "whip-learn"
    if "/research" in t or "/조사" in t:
        return "whip-research"
    if "/think" in t or "/분석" in t:
        return "whip-think"
    if "/medical" in t or "/의료" in t:
        return "whip-medical"
    return "whip"


def clean_mention(text: str) -> str:
    """@whipper 멘션 태그 제거."""
    return re.sub(r"<@[A-Z0-9]+>", "", text).strip()


def create_app():
    cfg = load_slack_config()
    if not cfg.get("bot_token") or not cfg.get("app_token"):
        logger.error("Slack tokens not configured. Run /whipper:whip-notion-init first.")
        sys.exit(1)

    app = App(token=cfg["bot_token"])
    bot_user_id = cfg.get("bot_user_id", "")

    # 봇이 응답한 스레드 추적 (인메모리, 재시작 시 리셋)
    responded_threads: set = set()

    def spawn_claude(prompt: str, skill: str, channel: str, thread_ts: str):
        """별도 스레드에서 claude CLI 실행, 결과를 Slack에 회신."""

        def run():
            try:
                app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"🔥 작업 시작... (/{skill})",
                )

                full_prompt = f"/whipper:{skill} {prompt}"
                result = subprocess.run(
                    ["claude", "-p", full_prompt],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    cwd=os.path.expanduser("~"),
                )

                output = result.stdout
                if len(output) > 3000:
                    output = output[-3000:]

                status_emoji = "✅ 완료!" if result.returncode == 0 else "❌ 오류"
                msg = f"{status_emoji}\n\n{output}" if output.strip() else status_emoji

                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=msg
                )
            except subprocess.TimeoutExpired:
                app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text="⏰ 시간 초과 (10분). 스레드에 답장으로 이어서 진행 가능.",
                )
            except Exception as e:
                logger.error(f"spawn error: {e}")
                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=f"❌ 오류: {e}"
                )

        threading.Thread(target=run, daemon=True).start()

    @app.event("app_mention")
    def handle_mention(event, say):
        """@whipper 멘션 처리."""
        text = clean_mention(event.get("text", ""))
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        if not text:
            say(text="무엇을 도와드릴까요?", thread_ts=thread_ts)
            return

        # Slack thread 컨텍스트를 프롬프트에 포함
        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_claude(slack_context + text, skill, channel, thread_ts)
        responded_threads.add(thread_ts)

    @app.event("message")
    def handle_message(event, say):
        """스레드 답장 처리 (멘션 없이도, 봇이 이전에 응답한 스레드만)."""
        if event.get("bot_id") or event.get("user") == bot_user_id:
            return
        thread_ts = event.get("thread_ts")
        if not thread_ts or thread_ts not in responded_threads:
            return

        text = event.get("text", "")
        channel = event["channel"]
        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_claude(slack_context + text, skill, channel, thread_ts)

    return app, cfg


def main():
    app, cfg = create_app()
    handler = SocketModeHandler(app, cfg["app_token"])
    logger.info("🔥 Whipper Slack Bot started (Socket Mode)")
    handler.start()


if __name__ == "__main__":
    main()
