#!/usr/bin/env python3
"""tests/test_scheduler.py — scheduler unit tests."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "daemon"))

from claude_runtime import EMPTY_MCP_CONFIG
from scheduler import (
    acquire_run_lock,
    build_followup_dispatch_prompt,
    build_followup_prompt,
    build_todo_prompt,
    extract_thread_root_text,
    load_scheduler_config,
    normalize_root_text,
    reconcile_stale_candidate,
    release_run_lock,
    run_scheduled_followups,
    run_todo_check,
    thread_has_completion,
)


def test_load_scheduler_config_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "missing.json"
        cfg = load_scheduler_config(config_path)
        todo = cfg["todo_check"]
        assert todo["enabled"] is True
        assert todo["interval_minutes"] == 120
        assert todo["timeout_seconds"] == 300
        assert todo["dry_run"] is False
        assert todo["run_on_start"] is False
        assert todo["extra_prompt_args"] == []


def test_load_scheduler_config_file_and_env_override():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "daemon.json"
        config_path.write_text(
            json.dumps(
                {
                    "todo_check": {
                        "enabled": False,
                        "interval_minutes": 15,
                        "timeout_seconds": 90,
                        "dry_run": False,
                        "run_on_start": False,
                        "extra_prompt_args": ["--limit", "2"],
                    }
                }
            )
        )

        old_env = os.environ.copy()
        os.environ["WHIPPER_TODO_ENABLED"] = "true"
        os.environ["WHIPPER_TODO_DRY_RUN"] = "1"
        os.environ["WHIPPER_TODO_EXTRA_ARGS"] = "--alpha beta"
        try:
            cfg = load_scheduler_config(config_path)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        todo = cfg["todo_check"]
        assert todo["enabled"] is True
        assert todo["interval_minutes"] == 15
        assert todo["timeout_seconds"] == 90
        assert todo["dry_run"] is True
        assert todo["extra_prompt_args"] == ["--alpha", "beta"]


def test_build_todo_prompt():
    cfg = {
        "todo_check": {
            "enabled": True,
            "interval_minutes": 1,
            "timeout_seconds": 60,
            "dry_run": True,
            "run_on_start": False,
            "extra_prompt_args": ["--limit", "2"],
        }
    }
    assert build_todo_prompt(cfg) == "/whipper:whip-todo --dry-run --limit 2"


def test_build_followup_dispatch_prompt():
    candidate = {
        "page_id": "page123",
        "name": "Existing Task",
        "skill": "whip",
        "channel": "C123",
        "thread_ts": "1774434726.092599",
        "age_minutes": 42,
        "followup_kind": "blocked",
    }
    prompt = build_followup_dispatch_prompt(candidate)
    assert prompt.startswith("[Slack thread: C123/1774434726.092599] ")
    assert build_followup_prompt(candidate) in prompt


def test_extract_thread_root_text():
    messages = [
        {"text": "<@U123> /medical 가벼운 두통과 콧물일 때 세 줄로 알려줘 *Sent using* Claude"}
    ]
    assert normalize_root_text(messages[0]["text"]) == "/medical 가벼운 두통과 콧물일 때 세 줄로 알려줘"
    assert extract_thread_root_text(messages) == "/medical 가벼운 두통과 콧물일 때 세 줄로 알려줘"


def test_run_todo_check_invokes_claude():
    cfg = {
        "todo_check": {
            "enabled": True,
            "interval_minutes": 1,
            "timeout_seconds": 45,
            "dry_run": True,
            "run_on_start": False,
            "extra_prompt_args": ["--limit", "2"],
        }
    }

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    with tempfile.TemporaryDirectory() as tmp:
        with patch("scheduler.LOCK_PATH", Path(tmp) / "run.lock"):
            with patch("scheduler.subprocess.run", return_value=Result()) as mock_run:
                result = run_todo_check(cfg)

    assert result is not None
    args = mock_run.call_args[0][0]
    env = mock_run.call_args.kwargs["env"]
    assert args[:6] == [
        "claude",
        "--plugin-dir",
        str(ROOT),
        "--strict-mcp-config",
        "--mcp-config",
        EMPTY_MCP_CONFIG,
    ]
    assert args[6:8] == ["--permission-mode", "bypassPermissions"]
    assert args[-2:] == ["-p", "/whipper:whip-todo --dry-run --limit 2"]
    assert env["CLAUDE_PLUGIN_ROOT"] == str(ROOT)


def test_run_scheduled_followups_passes_slack_context():
    cfg = {
        "todo_check": {
            "enabled": True,
            "interval_minutes": 1,
            "timeout_seconds": 60,
            "dry_run": False,
            "run_on_start": False,
            "extra_prompt_args": [],
            "stale_minutes": 120,
            "blocked_cooldown_minutes": 30,
            "max_tasks_per_run": 1,
            "include_blocked": True,
            "include_in_progress": True,
        }
    }
    candidate = {
        "page_id": "page123",
        "name": "Existing Task",
        "skill": "whip-think",
        "status": "블락드",
        "channel": "C123",
        "thread_ts": "1774434726.092599",
        "slack_url": "https://learnerscompany.slack.com/archives/C123/p1774434726092599",
        "last_edited_time": "2026-03-25T00:00:00.000Z",
        "age_minutes": 120,
        "followup_kind": "blocked",
        "priority": 0,
    }

    with patch("scheduler.list_followup_candidates", return_value=[candidate]):
        with patch("scheduler.load_slack_config", return_value={"bot_token": "xoxb-test"}):
            with patch("scheduler.App") as mock_app:
                with patch("scheduler.SlackBridge"):
                    with patch(
                        "scheduler.get_thread_messages",
                        return_value=[{"text": "<@U123> /think Existing Task *Sent using* Claude"}],
                    ):
                        with patch("scheduler.run_dispatch") as mock_dispatch:
                            app_instance = mock_app.return_value
                            app_instance.client = object()
                            result = run_scheduled_followups(cfg)

    assert result == [
        {
            **candidate,
            "thread_messages": [{"text": "<@U123> /think Existing Task *Sent using* Claude"}],
            "root_text": "/think Existing Task",
            "followup_action": "dispatched",
        }
    ]
    prompt = mock_dispatch.call_args.args[2]
    assert prompt.startswith("[Slack thread: C123/1774434726.092599] ")
    assert "/think Existing Task" in prompt
    assert "[scheduled follow-up page:page123]" in prompt
    assert mock_dispatch.call_args.args[3:] == ("whip-think", "C123", "1774434726.092599")


def test_thread_has_completion():
    assert thread_has_completion(
        [
            {"text": "중간 메시지"},
            {"text": "✅ 작업 완료!"},
        ]
    ) is True


def test_reconcile_stale_candidate_updates_notion():
    candidate = {
        "page_id": "page123",
        "channel": "C123",
        "thread_ts": "1774434726.092599",
        "followup_kind": "stale_in_progress",
        "thread_messages": [{"text": "✅ 작업 완료!"}],
    }

    class SlackClient:
        def __init__(self):
            self.posted = []

        def chat_postMessage(self, channel, thread_ts, text):
            self.posted.append((channel, thread_ts, text))

    slack_client = SlackClient()

    class Response:
        status_code = 200

    with patch("scheduler.notion_patch", return_value=Response()) as mock_patch:
        reconciled = reconcile_stale_candidate(slack_client, candidate)

    assert reconciled is True
    assert mock_patch.call_args.args[0] == "pages/page123"
    assert slack_client.posted == [
        ("C123", "1774434726.092599", "🧾 이전 완료 상태를 확인해 Notion 상태를 완료로 동기화했습니다.")
    ]


def test_run_lock_nonblocking():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("scheduler.LOCK_PATH", Path(tmp) / "run.lock"):
            first = acquire_run_lock(blocking=False)
            assert first is not None
            try:
                second = acquire_run_lock(blocking=False)
                assert second is None
            finally:
                release_run_lock(first)


if __name__ == "__main__":
    passed = failed = 0
    for name in sorted([n for n in dir() if n.startswith("test_") and callable(globals()[n])]):
        try:
            globals()[name]()
            print(f"✅ {name}")
            passed += 1
        except Exception as e:
            print(f"❌ {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
