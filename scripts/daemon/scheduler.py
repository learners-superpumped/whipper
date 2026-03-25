#!/usr/bin/env python3
"""Periodic follow-up scheduler for whipper."""
import json
import logging
import os
import re
import shlex
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from slack_bolt import App

logger = logging.getLogger("whipper-scheduler")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "daemon.json"
import sys

sys.path.insert(0, str(ROOT_DIR))

try:
    from .claude_runtime import build_claude_print_command
    from .dispatch import load_slack_config, run_dispatch
    from . import run_lock as run_lock_module
except ImportError:
    from claude_runtime import build_claude_print_command
    from dispatch import load_slack_config, run_dispatch
    import run_lock as run_lock_module
from scripts.notion.api import (
    get_database_id,
    load_config as load_notion_config,
    notion_patch,
    notion_post,
    to_uuid,
)
from scripts.core.local_env import export_whipper_aliases
from scripts.slack.bridge import SlackBridge

LOCK_PATH = run_lock_module.LOCK_PATH

DEFAULT_CONFIG = {
    "todo_check": {
        "enabled": True,
        "interval_minutes": 120,
        "timeout_seconds": 300,
        "dry_run": False,
        "run_on_start": False,
        "extra_prompt_args": [],
        "stale_minutes": 120,
        "blocked_cooldown_minutes": 30,
        "max_tasks_per_run": 3,
        "include_blocked": True,
        "include_in_progress": True,
    }
}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Ignoring invalid integer for %s: %s", name, value)
        return default


def load_scheduler_config(config_path: Path = CONFIG_PATH) -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))

    if config_path.exists():
        file_config = json.loads(config_path.read_text())
        todo_config = file_config.get("todo_check", {})
        if isinstance(todo_config, dict):
            config["todo_check"].update(todo_config)

    todo = config["todo_check"]
    todo["enabled"] = _env_flag("WHIPPER_TODO_ENABLED", bool(todo["enabled"]))
    todo["interval_minutes"] = max(
        1, _env_int("WHIPPER_TODO_INTERVAL_MINUTES", int(todo["interval_minutes"]))
    )
    todo["timeout_seconds"] = max(
        30, _env_int("WHIPPER_TODO_TIMEOUT_SECONDS", int(todo["timeout_seconds"]))
    )
    todo["dry_run"] = _env_flag("WHIPPER_TODO_DRY_RUN", bool(todo["dry_run"]))
    todo["run_on_start"] = _env_flag(
        "WHIPPER_TODO_RUN_ON_START", bool(todo["run_on_start"])
    )

    extra_args = todo.get("extra_prompt_args", [])
    env_extra_args = os.getenv("WHIPPER_TODO_EXTRA_ARGS")
    if env_extra_args:
        extra_args = shlex.split(env_extra_args)
    elif isinstance(extra_args, str):
        extra_args = shlex.split(extra_args)
    elif not isinstance(extra_args, list):
        extra_args = []
    todo["extra_prompt_args"] = [str(arg) for arg in extra_args]
    todo["stale_minutes"] = max(
        1, _env_int("WHIPPER_TODO_STALE_MINUTES", int(todo["stale_minutes"]))
    )
    todo["blocked_cooldown_minutes"] = max(
        1,
        _env_int(
            "WHIPPER_TODO_BLOCKED_COOLDOWN_MINUTES",
            int(todo["blocked_cooldown_minutes"]),
        ),
    )
    todo["max_tasks_per_run"] = max(
        1, _env_int("WHIPPER_TODO_MAX_TASKS", int(todo["max_tasks_per_run"]))
    )
    todo["include_blocked"] = _env_flag(
        "WHIPPER_TODO_INCLUDE_BLOCKED", bool(todo["include_blocked"])
    )
    todo["include_in_progress"] = _env_flag(
        "WHIPPER_TODO_INCLUDE_IN_PROGRESS", bool(todo["include_in_progress"])
    )
    return config


def build_todo_prompt(config: dict | None = None) -> str:
    todo = (config or load_scheduler_config())["todo_check"]
    parts = ["/whipper:whip-todo"]
    if todo.get("dry_run"):
        parts.append("--dry-run")
    parts.extend(todo.get("extra_prompt_args", []))
    return " ".join(parts)


def acquire_run_lock(blocking: bool = True):
    run_lock_module.LOCK_PATH = LOCK_PATH
    return run_lock_module.acquire_run_lock(blocking=blocking)


def release_run_lock(handle) -> None:
    return run_lock_module.release_run_lock(handle)


def _parse_notion_time(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _page_title(page: dict) -> str:
    title = page.get("properties", {}).get("Name", {}).get("title", [])
    return "".join(part.get("plain_text", "") for part in title)


def _parse_slack_thread_url(url: str) -> tuple[str, str] | None:
    match = re.match(r"^https://learnerscompany\.slack\.com/archives/([^/]+)/p(\d+)$", url or "")
    if not match:
        return None

    channel = match.group(1)
    digits = match.group(2)
    if len(digits) <= 6:
        return None
    thread_ts = f"{digits[:-6]}.{digits[-6:]}"
    return channel, thread_ts


def get_thread_messages(slack_client, channel: str, thread_ts: str) -> list[dict]:
    try:
        resp = slack_client.conversations_replies(channel=channel, ts=thread_ts, limit=100)
    except Exception as exc:
        logger.warning(
            "Failed to read Slack thread %s/%s: %s",
            channel,
            thread_ts,
            exc,
        )
        return []
    return resp.get("messages", [])


def normalize_root_text(text: str) -> str:
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text or "")
    cleaned = cleaned.replace("*Sent using* Claude", "")
    return " ".join(cleaned.split()).strip()


def extract_thread_root_text(messages: list[dict]) -> str:
    if not messages:
        return ""
    return normalize_root_text(messages[0].get("text", ""))


def _load_projects(statuses: list[str]) -> list[dict]:
    db_id = get_database_id()
    if not db_id or not statuses:
        return []

    filters = [{"property": "Status", "select": {"equals": status}} for status in statuses]
    body = {"page_size": 100, "filter": {"or": filters}}
    resp = notion_post(f"/databases/{db_id}/query", body)
    if resp is None or resp.status_code != 200:
        logger.warning("Failed to query Notion follow-up candidates")
        return []
    return resp.json().get("results", [])


def list_followup_candidates(config: dict | None = None) -> list[dict]:
    cfg = config or load_scheduler_config()
    todo = cfg["todo_check"]
    notion_cfg = load_notion_config()
    statuses = []
    if todo.get("include_blocked", True):
        statuses.append(notion_cfg.get("status_mapping", {}).get("blocked", "블락드"))
    if todo.get("include_in_progress", True):
        statuses.append(notion_cfg.get("status_mapping", {}).get("in_progress", "진행중"))

    now = datetime.now(timezone.utc)
    blocked_status = notion_cfg.get("status_mapping", {}).get("blocked", "블락드")
    in_progress_status = notion_cfg.get("status_mapping", {}).get("in_progress", "진행중")
    stale_minutes = int(todo["stale_minutes"])
    blocked_cooldown_minutes = int(todo["blocked_cooldown_minutes"])
    candidates = []

    for page in _load_projects(statuses):
        props = page.get("properties", {})
        status = (props.get("Status", {}).get("select") or {}).get("name", "")
        skill = (props.get("Skill", {}).get("select") or {}).get("name", "whip")
        slack_url = props.get("Slack Thread", {}).get("url") or ""
        parsed_thread = _parse_slack_thread_url(slack_url)
        if not parsed_thread:
            continue

        last_edited_raw = page.get("last_edited_time")
        if not last_edited_raw:
            continue
        last_edited = _parse_notion_time(last_edited_raw)
        age_minutes = (now - last_edited).total_seconds() / 60

        followup_kind = ""
        priority = 99
        if status == blocked_status and age_minutes >= blocked_cooldown_minutes:
            followup_kind = "blocked"
            priority = 0
        elif status == in_progress_status and age_minutes >= stale_minutes:
            followup_kind = "stale_in_progress"
            priority = 1

        if not followup_kind:
            continue

        channel, thread_ts = parsed_thread
        candidates.append(
            {
                "page_id": page["id"].replace("-", ""),
                "name": _page_title(page),
                "skill": skill or "whip",
                "status": status,
                "channel": channel,
                "thread_ts": thread_ts,
                "slack_url": slack_url,
                "last_edited_time": last_edited_raw,
                "age_minutes": int(age_minutes),
                "followup_kind": followup_kind,
                "priority": priority,
            }
        )

    candidates.sort(key=lambda item: (item["priority"], -item["age_minutes"], item["name"]))
    return candidates[: int(todo["max_tasks_per_run"])]


def build_followup_prompt(candidate: dict) -> str:
    name = candidate.get("root_text") or candidate["name"]
    page_id = candidate["page_id"]
    age_minutes = candidate["age_minutes"]
    if candidate["followup_kind"] == "blocked":
        return (
            f"[scheduled follow-up page:{page_id}] 이전 블락드 작업을 재검토하고 "
            f"가능하면 이어서 완료해줘. 아직 블락이면 지금 필요한 사용자 입력이나 다음 조치를 "
            f"스레드에 명확히 남겨줘. 원래 작업의 형식과 범위는 절대 넓히지 말고 그대로 유지해줘. "
            f"예를 들어 한 줄/세 줄/출처 개수 요구가 있으면 그 요구를 그대로 지켜. 원래 작업: {name}"
        )
    return (
        f"[scheduled follow-up page:{page_id}] {age_minutes}분 이상 갱신되지 않은 진행중 작업을 "
        f"재개해서 완료 또는 블락 상태 정리까지 진행해줘. 원래 작업의 형식과 범위는 절대 넓히지 말고 "
        f"그대로 유지해줘. 예를 들어 한 줄/세 줄/출처 개수 요구가 있으면 그 요구를 그대로 지켜. "
        f"원래 작업: {name}"
    )


def build_followup_dispatch_prompt(candidate: dict) -> str:
    slack_context = f"[Slack thread: {candidate['channel']}/{candidate['thread_ts']}] "
    return slack_context + build_followup_prompt(candidate)


def thread_has_completion(messages: list[dict]) -> bool:
    completion_markers = ("작업 완료", "전체 통과", "조사 완료:")
    for message in messages:
        text = message.get("text", "")
        if any(marker in text for marker in completion_markers):
            return True
    return False


def sync_notion_status(page_id: str, status: str) -> bool:
    response = notion_patch(
        f"pages/{to_uuid(page_id)}",
        {"properties": {"Status": {"select": {"name": status}}}},
    )
    return response is not None and response.status_code == 200


def reconcile_stale_candidate(slack_client, candidate: dict) -> bool:
    messages = candidate.get("thread_messages") or get_thread_messages(
        slack_client, candidate["channel"], candidate["thread_ts"]
    )
    if not thread_has_completion(messages):
        return False

    if sync_notion_status(candidate["page_id"], "완료"):
        logger.info(
            "Reconciled stale task as completed from Slack thread: %s/%s",
            candidate["channel"],
            candidate["thread_ts"],
        )
        slack_client.chat_postMessage(
            channel=candidate["channel"],
            thread_ts=candidate["thread_ts"],
            text="🧾 이전 완료 상태를 확인해 Notion 상태를 완료로 동기화했습니다.",
        )
        return True

    logger.warning(
        "Failed to reconcile stale task status in Notion for page=%s",
        candidate["page_id"],
    )
    return False


def run_scheduled_followups(config: dict | None = None) -> list[dict]:
    cfg = config or load_scheduler_config()
    todo = cfg["todo_check"]
    if not todo.get("enabled", True):
        logger.info("Todo follow-up scheduler disabled; skipping follow-up cycle.")
        return []

    candidates = list_followup_candidates(cfg)
    if not candidates:
        logger.info("No scheduled follow-up candidates found.")
        return []

    logger.info(
        "Scheduled follow-up candidates: %s",
        ", ".join(
            f"{c['followup_kind']}:{c['skill']}:{c['channel']}/{c['thread_ts']}"
            for c in candidates
        ),
    )
    if todo.get("dry_run"):
        return candidates

    slack_cfg = load_slack_config()
    app = App(token=slack_cfg["bot_token"])
    bridge = SlackBridge(app.client)

    dispatched = []
    for candidate in candidates:
        thread_messages = get_thread_messages(
            app.client, candidate["channel"], candidate["thread_ts"]
        )
        enriched = {
            **candidate,
            "thread_messages": thread_messages,
            "root_text": extract_thread_root_text(thread_messages),
        }
        if reconcile_stale_candidate(app.client, enriched):
            dispatched.append({**enriched, "followup_action": "reconciled_complete"})
            continue

        prompt = build_followup_dispatch_prompt(enriched)
        run_dispatch(
            app.client,
            bridge,
            prompt,
            enriched["skill"],
            enriched["channel"],
            enriched["thread_ts"],
        )
        dispatched.append({**enriched, "followup_action": "dispatched"})
    return dispatched


def run_todo_check(config: dict | None = None) -> subprocess.CompletedProcess | None:
    cfg = config or load_scheduler_config()
    todo = cfg["todo_check"]

    if not todo.get("enabled", True):
        logger.info("Todo follow-up scheduler disabled; skipping run.")
        return None

    prompt = build_todo_prompt(cfg)
    command = build_claude_print_command(
        prompt,
        ROOT_DIR,
        permission_mode="bypassPermissions",
    )

    lock_handle = acquire_run_lock(blocking=False)
    if lock_handle is None:
        logger.info("Skipping todo follow-up check because another whipper run is active.")
        return None

    try:
        claude_env = export_whipper_aliases(os.environ.copy())
        claude_env["CLAUDE_PLUGIN_ROOT"] = str(ROOT_DIR)
        result = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=int(todo["timeout_seconds"]),
            env=claude_env,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "Todo follow-up check timed out after %ss", todo["timeout_seconds"]
        )
        return None
    except Exception as exc:
        logger.error("Todo follow-up check failed: %s", exc)
        return None
    finally:
        release_run_lock(lock_handle)

    output = (result.stdout or result.stderr or "").strip()
    if len(output) > 400:
        output = "..." + output[-400:]
    logger.info(
        "Todo follow-up check finished (exit=%s, prompt=%s)%s",
        result.returncode,
        prompt,
        f" output={output}" if output else "",
    )
    return result


class TodoScheduler:
    """Simple interval scheduler for periodic todo follow-up."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_scheduler_config()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def interval_seconds(self) -> int:
        return int(self.config["todo_check"]["interval_minutes"]) * 60

    def start(self):
        if not self.config["todo_check"].get("enabled", True):
            logger.info("Todo follow-up scheduler disabled in config.")
            return self
        if self._thread and self._thread.is_alive():
            return self

        if self.config["todo_check"].get("run_on_start"):
            run_scheduled_followups(self.config)

        self._thread = threading.Thread(
            target=self._loop,
            name="whipper-todo-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "📋 Scheduler started (todo follow-up every %sm)",
            self.config["todo_check"]["interval_minutes"],
        )
        return self

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _loop(self):
        while not self._stop.wait(self.interval_seconds):
            run_scheduled_followups(self.config)


def start_scheduler(config_path: Path = CONFIG_PATH) -> TodoScheduler:
    return TodoScheduler(load_scheduler_config(config_path)).start()
