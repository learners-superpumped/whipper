#!/usr/bin/env python3
"""Whipper Slack Bot — 얇은 릴레이 + Slack 브릿지.

역할: Slack 이벤트 수신 → claude CLI spawn → 브릿지가 중간 보고 → 최종 결과 회신.
Notion/프로젝트 로직 = 0. 모든 지능은 Claude 세션 안에서.
"""
import glob
import os
import sys
import json
import re
import subprocess
import threading
import time
import logging
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("whipper-daemon")

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# Add parent dirs to path for bridge import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.slack.bridge import SlackBridge


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
    bridge = SlackBridge(app.client)

    # 봇이 응답한 스레드 추적 (인메모리, 재시작 시 리셋)
    responded_threads: set = set()

    def spawn_claude(prompt: str, skill: str, channel: str, thread_ts: str):
        """별도 스레드에서 claude CLI 실행, 브릿지로 중간 보고, 최종 결과 회신."""

        def run():
            try:
                app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"🔥 작업 시작... (/{skill})",
                )

                full_prompt = f"/whipper:{skill} {prompt}"
                process = subprocess.Popen(
                    ["claude", "-p", full_prompt],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=os.path.expanduser("~"),
                )

                # 브릿지: claude가 setup.sh로 task_dir을 만들면 감시 시작
                # 약간 대기 후 최신 task_dir 찾기
                time.sleep(10)
                task_dirs = sorted(
                    glob.glob("/tmp/whipper-*"),
                    key=os.path.getmtime,
                    reverse=True,
                )
                if task_dirs and os.path.isdir(task_dirs[0] + "/slack_messages"):
                    bridge.watch(task_dirs[0], channel, thread_ts)
                    logger.info(f"Bridge started for: {task_dirs[0]}")

                # 프로세스 완료 대기 (30분 타임아웃, 5분 간격 핑)
                # State 파일이 생성된 후 삭제되면 PASS → 60초 후 kill
                timeout = 1800
                start = time.time()
                last_ping = start
                pass_detected_at = None
                state_file_ever_existed = False
                state_file = Path(os.path.expanduser("~")) / ".claude" / "whipper.local.md"

                while process.poll() is None:
                    elapsed = time.time() - start
                    if elapsed > timeout:
                        process.kill()
                        app.client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=f"⏰ 시간 초과 ({timeout // 60}분).",
                        )
                        return

                    # State 파일 존재 추적
                    if state_file.exists():
                        state_file_ever_existed = True

                    # PASS 감지: state 파일이 한번 존재했다가 삭제된 경우만
                    if state_file_ever_existed and not state_file.exists() and pass_detected_at is None:
                        pass_detected_at = time.time()
                        logger.info("PASS detected (state file created then deleted). Waiting 60s...")

                    # PASS 후 60초 지나면 강제 종료
                    if pass_detected_at and (time.time() - pass_detected_at > 60):
                        logger.info("Force-killing claude after PASS grace period.")
                        process.kill()
                        break

                    if time.time() - last_ping > 300 and pass_detected_at is None:
                        mins = int(elapsed // 60)
                        app.client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=f"⏳ 작업 진행중... ({mins}분 경과)",
                        )
                        last_ping = time.time()
                    time.sleep(5)

                # 최종 결과 (브릿지가 중간 보고를 했으므로 요약만)
                output = process.stdout.read()
                if len(output) > 500:
                    output = "...\n" + output[-500:]

                status_emoji = "✅ 작업 완료!" if process.returncode == 0 else "❌ 오류 발생"
                msg = f"{status_emoji}\n```\n{output}\n```" if output.strip() else status_emoji

                app.client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=msg
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
