#!/usr/bin/env python3
"""Whipper Slack Bot — 얇은 릴레이 + Slack 브릿지.

역할: Slack 이벤트 수신 → claude CLI spawn → 브릿지가 중간 보고 → 최종 결과 회신.
Notion/프로젝트 로직 = 0. 모든 지능은 Claude 세션 안에서.
"""
import os
import sys
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

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATE_FILE = Path(os.path.expanduser("~")) / ".claude" / "whipper.local.md"

# Add parent dirs to path for bridge import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.slack.bridge import SlackBridge
from scripts.core.local_env import export_whipper_aliases
from scripts.core.runtime_config import build_slack_thread_url, load_slack_config

try:
    from .claude_runtime import (
        build_claude_print_command,
        cleanup_output_log,
        create_output_log,
        read_output_tail,
    )
    from .run_lock import acquire_run_lock, release_run_lock
    from .scheduler import start_scheduler
    from . import dispatch as dispatch_module
    from .dispatch import lookup_thread_page
except ImportError:
    from claude_runtime import (
        build_claude_print_command,
        cleanup_output_log,
        create_output_log,
        read_output_tail,
    )
    from run_lock import acquire_run_lock, release_run_lock
    from scheduler import start_scheduler
    import dispatch as dispatch_module
    from dispatch import lookup_thread_page


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


def should_handle_followup_thread(
    thread_ts: str | None,
    responded_threads: set,
    existing_thread: dict | None = None,
) -> bool:
    if not thread_ts:
        return False
    if thread_ts in responded_threads:
        return True
    if not existing_thread:
        return False
    responded_threads.add(thread_ts)
    return True


def resolve_final_state(
    final_marker: str | None, returncode: int | None, timed_out: bool
) -> tuple[str, str]:
    """Resolve the task outcome for Slack/Notion reporting."""
    if timed_out:
        return "blocked", "timeout"
    if final_marker == "passed":
        return "passed", "passed"
    if final_marker in {"blocked", "failed", "max_iterations"}:
        return "blocked", final_marker
    if returncode == 0:
        return "passed", "exit_0"
    return "blocked", "nonzero_exit"


def notion_status_for(final_state: str) -> str:
    return "완료" if final_state == "passed" else "블락드"


def build_slack_url(channel: str, thread_ts: str) -> str:
    workspace_domain = load_slack_config().get("workspace_domain", "")
    return build_slack_thread_url(workspace_domain, channel, thread_ts)


def build_final_slack_message(final_state: str, reason: str, output: str) -> str:
    if final_state == "passed":
        return "✅ 작업 완료!"

    prefix = {
        "timeout": "⏰ 시간 초과. 후속 확인이 필요합니다.",
        "max_iterations": "🚫 최대 iteration에 도달했습니다. 스레드에 답장 주시면 이어서 진행합니다.",
        "failed": "🚫 작업이 블락되었습니다. 스레드에 추가 지시를 남겨주세요.",
        "blocked": "🚫 작업이 블락되었습니다. 스레드에 추가 지시를 남겨주세요.",
        "nonzero_exit": "❌ 오류로 중단되었습니다. 스레드에 추가 지시를 남겨주세요.",
    }.get(reason, "🚫 추가 확인이 필요합니다. 스레드에 지시를 남겨주세요.")

    if not output.strip():
        return prefix
    return f"{prefix}\n```\n{output}\n```"


def extract_frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not match:
        return ""

    value = match.group(1).strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_thread_lookup_result(raw: str) -> dict | None:
    line = (raw or "").strip()
    if not line or line == "NOT_FOUND":
        return None

    parts = line.split("\t")
    if len(parts) < 4:
        return None

    page_id, name, iteration, status = parts[:4]
    try:
        iteration_value = int(iteration or 0)
    except ValueError:
        iteration_value = 0

    return {
        "page_id": page_id,
        "name": name,
        "iteration": iteration_value,
        "status": status,
    }


def determine_thread_page(prompt: str, skill: str, channel: str, thread_ts: str) -> dict:
    slack_url = build_slack_url(channel, thread_ts)

    query = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "notion" / "query_thread.py"), slack_url],
        capture_output=True,
        text=True,
        timeout=15,
    )
    existing = parse_thread_lookup_result(query.stdout)
    if existing:
        page_id = existing["page_id"]
        return {
            "mode": "existing",
            "page_id": page_id,
            "notion_url": f"https://www.notion.so/{page_id}",
            "name": existing["name"],
            "iteration": existing["iteration"],
            "status": existing["status"],
        }

    name = prompt.split("]")[-1].strip()[:50] if "]" in prompt else prompt[:50]
    create = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "notion" / "create_page.py"),
            "--name",
            name or "Whipper Task",
            "--skill",
            skill,
            "--slack-url",
            slack_url,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    parts = create.stdout.strip().split()
    if len(parts) >= 2 and parts[0] not in ("FAILED", "NO_DB", "NO_TOKEN"):
        page_id, notion_url = parts[0], parts[1]
        logger.info("Notion page created: %s", notion_url)
        return {
            "mode": "new",
            "page_id": page_id,
            "notion_url": notion_url,
            "name": name or "Whipper Task",
            "iteration": 1,
            "status": "진행중",
        }

    if create.stdout.strip():
        logger.warning("Notion page provisioning skipped: %s", create.stdout.strip())
    if create.stderr.strip():
        logger.warning("Notion page provisioning stderr: %s", create.stderr.strip())
    return {
        "mode": "unknown",
        "page_id": "",
        "notion_url": "",
        "name": "",
        "iteration": 0,
        "status": "",
    }


def apply_thread_page_env(env: dict, thread_page: dict) -> dict:
    applied = dict(env)
    applied["WHIPPER_THREAD_PAGE_MODE"] = thread_page.get("mode", "unknown")
    applied["WHIPPER_NOTION_PAGE_ID"] = thread_page.get("page_id", "")
    applied["WHIPPER_NOTION_PAGE_URL"] = thread_page.get("notion_url", "")
    applied["WHIPPER_THREAD_PAGE_NAME"] = thread_page.get("name", "")
    applied["WHIPPER_THREAD_PAGE_ITERATION"] = str(thread_page.get("iteration", 0))
    applied["WHIPPER_THREAD_PAGE_STATUS"] = thread_page.get("status", "")
    return applied


def wait_for_task_dir(state_file: Path, expected_thread_ts: str, timeout_seconds: int = 30) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if not state_file.exists():
                time.sleep(1)
                continue

            frontmatter = state_file.read_text()
            if expected_thread_ts not in frontmatter:
                time.sleep(1)
                continue

            task_dir = extract_frontmatter_value(frontmatter, "task_dir")
            if task_dir and os.path.isdir(task_dir) and os.path.isdir(os.path.join(task_dir, "slack_messages")):
                return task_dir
        except OSError:
            pass

        time.sleep(1)

    return ""


def detect_latest_iteration(task_dir: str) -> int:
    iterations_dir = Path(task_dir) / "iterations"
    latest = 0
    if not iterations_dir.is_dir():
        return latest

    for path in iterations_dir.glob("*.md"):
        match = re.match(r"^(\d+)-", path.name)
        if not match:
            continue
        latest = max(latest, int(match.group(1)))
    return latest


def run_dispatch(slack_client, bridge: SlackBridge, prompt: str, skill: str, channel: str, thread_ts: str):
    lock_handle = None
    output_handle = None
    output_path = None
    try:
        lock_handle = acquire_run_lock(blocking=False)
        if lock_handle is None:
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="⏸️ 다른 작업이 실행 중이라 대기열에 넣었습니다.",
            )
            lock_handle = acquire_run_lock(blocking=True)

        logger.info(
            "Dispatching skill=%s channel=%s thread=%s prompt=%s",
            skill,
            channel,
            thread_ts,
            prompt[:120],
        )
        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"🔥 작업 시작... (/{skill})",
        )

        thread_page = determine_thread_page(prompt, skill, channel, thread_ts)
        full_prompt = f"/whipper:{skill} {prompt}"
        claude_env = export_whipper_aliases(os.environ.copy())
        claude_env["CLAUDE_PLUGIN_ROOT"] = str(ROOT_DIR)
        claude_env = apply_thread_page_env(claude_env, thread_page)
        output_handle, output_path = create_output_log()
        process = subprocess.Popen(
            build_claude_print_command(
                full_prompt,
                ROOT_DIR,
                permission_mode="bypassPermissions",
            ),
            stdout=output_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=os.path.expanduser("~"),
            env=claude_env,
        )

        task_dir_found = wait_for_task_dir(STATE_FILE, thread_ts, timeout_seconds=30)
        if task_dir_found:
            bridge.watch(task_dir_found, channel, thread_ts)
            logger.info("Bridge started for: %s", task_dir_found)
            if thread_page.get("page_id"):
                Path(task_dir_found, ".notion_page_id").write_text(thread_page["page_id"])
        else:
            logger.warning("No task_dir with slack_messages/ found after 30s")

        notion_page_id = thread_page.get("page_id", "")

        timeout = 1800
        start = time.time()
        last_ping = start
        final_status_detected_at = None
        final_status_marker = ""
        timed_out = False
        while process.poll() is None:
            elapsed = time.time() - start
            if elapsed > timeout:
                timed_out = True
                process.kill()
                try:
                    process.wait(timeout=10)
                except Exception:
                    pass
                slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"⏰ 시간 초과 ({timeout // 60}분).",
                )
                break

            if task_dir_found and not STATE_FILE.exists() and final_status_detected_at is None:
                marker_path = Path(task_dir_found) / ".final_status"
                if marker_path.exists():
                    final_status_marker = marker_path.read_text().strip()
                else:
                    final_status_marker = "passed"
                final_status_detected_at = time.time()
                wait_seconds = 60 if final_status_marker == "passed" else 10
                logger.info(
                    "Final state detected: %s. Waiting %ss before forcing exit.",
                    final_status_marker,
                    wait_seconds,
                )

            if final_status_detected_at:
                wait_seconds = 60 if final_status_marker == "passed" else 10
                if time.time() - final_status_detected_at > wait_seconds:
                    logger.info(
                        "Force-killing claude after final state=%s",
                        final_status_marker or "unknown",
                    )
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except Exception:
                        pass
                    break

            if time.time() - last_ping > 300 and not final_status_detected_at:
                mins = int(elapsed // 60)
                slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"⏳ 작업 진행중... ({mins}분 경과)",
                )
                last_ping = time.time()
            time.sleep(5)

        if output_handle is not None:
            output_handle.flush()
            output_handle.close()
            output_handle = None
        output = read_output_tail(output_path) if output_path else ""

        final_state, final_reason = resolve_final_state(
            final_status_marker or None, process.returncode, timed_out
        )

        if notion_page_id and task_dir_found and os.path.isdir(task_dir_found):
            try:
                latest_iteration = detect_latest_iteration(task_dir_found)
                upload_args = [
                    sys.executable,
                    str(SCRIPTS_DIR / "notion" / "upload_task.py"),
                    notion_page_id,
                    task_dir_found,
                    "--status",
                    notion_status_for(final_state),
                ]
                if latest_iteration > 0:
                    upload_args.extend(["--set-iteration", str(latest_iteration)])
                subprocess.run(
                    upload_args,
                    timeout=300,
                    check=True,
                )
                logger.info(
                    "Notion upload complete: %s from %s (status=%s)",
                    notion_page_id,
                    task_dir_found,
                    notion_status_for(final_state),
                )
            except Exception as e:
                logger.error("Notion upload failed: %s", e)
            import shutil
            shutil.rmtree(task_dir_found, ignore_errors=True)
            logger.info("Cleaned up: %s", task_dir_found)

        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=build_final_slack_message(final_state, final_reason, output),
        )
    except Exception as e:
        logger.error("spawn error: %s", e)
        slack_client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=f"❌ 오류: {e}"
        )
    finally:
        if output_handle is not None:
            output_handle.close()
        if output_path is not None:
            cleanup_output_log(output_path)
        release_run_lock(lock_handle)


def spawn_dispatch(slack_client, bridge: SlackBridge, prompt: str, skill: str, channel: str, thread_ts: str):
    threading.Thread(
        target=dispatch_module.run_dispatch,
        args=(slack_client, bridge, prompt, skill, channel, thread_ts),
        daemon=True,
    ).start()


def create_app():
    cfg = load_slack_config()
    if (
        not cfg.get("bot_token")
        or not cfg.get("app_token")
        or not cfg.get("workspace_domain")
    ):
        logger.error(
            "Slack config incomplete. Set bot/app tokens and workspace_domain, "
            "or run /whipper:whip-notion-init first."
        )
        sys.exit(1)

    app = App(token=cfg["bot_token"])
    bot_user_id = cfg.get("bot_user_id", "")
    bridge = SlackBridge(app.client)

    # 봇이 응답한 스레드 추적 (인메모리, 재시작 시 리셋)
    responded_threads: set = set()

    @app.event("app_mention")
    def handle_mention(event, say):
        """@whipper 멘션 처리."""
        text = clean_mention(event.get("text", ""))
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("Received app_mention channel=%s thread=%s", channel, thread_ts)

        if not text:
            say(text="무엇을 도와드릴까요?", thread_ts=thread_ts)
            return

        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_dispatch(app.client, bridge, slack_context + text, skill, channel, thread_ts)
        responded_threads.add(thread_ts)

    @app.event("message")
    def handle_message(event, say):
        """스레드 답장 처리 (멘션 없이도, 봇이 이전에 응답한 스레드만)."""
        if event.get("bot_id") or event.get("user") == bot_user_id:
            return
        thread_ts = event.get("thread_ts")
        channel = event["channel"]
        existing_thread = None
        if thread_ts not in responded_threads:
            existing_thread = lookup_thread_page(channel, thread_ts)
        if not should_handle_followup_thread(
            thread_ts, responded_threads, existing_thread
        ):
            return

        text = event.get("text", "")
        logger.info("Received follow-up message channel=%s thread=%s", channel, thread_ts)
        slack_context = f"[Slack thread: {channel}/{thread_ts}] "
        skill = detect_skill(text)
        spawn_dispatch(app.client, bridge, slack_context + text, skill, channel, thread_ts)

    return app, cfg


def main():
    app, cfg = create_app()
    start_scheduler()
    handler = SocketModeHandler(app, cfg["app_token"])
    logger.info("🔥 Whipper Slack Bot started (Socket Mode + scheduler)")
    handler.start()


if __name__ == "__main__":
    main()
