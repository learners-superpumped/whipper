#!/usr/bin/env python3
"""Runtime configuration helpers for local ignored files + env overrides."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.core.local_env import get_local_env_value

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_slack_workspace_domain(raw: str) -> str:
    domain = (raw or "").strip()
    if not domain:
        return ""
    if domain.startswith("https://"):
        domain = domain[len("https://"):]
    elif domain.startswith("http://"):
        domain = domain[len("http://"):]
    domain = domain.strip("/")
    if "/" in domain:
        domain = domain.split("/", 1)[0]
    if domain.endswith(".slack.com"):
        return domain
    if "." not in domain:
        return f"{domain}.slack.com"
    return domain


def build_slack_thread_url(workspace_domain: str, channel: str, thread_ts: str) -> str:
    domain = normalize_slack_workspace_domain(workspace_domain)
    if not domain:
        raise ValueError(
            "Slack workspace domain is not configured. Set WHIPPER_SLACK_WORKSPACE_DOMAIN "
            "or add workspace_domain to config/slack.json."
        )
    return f"https://{domain}/archives/{channel}/p{thread_ts.replace('.', '')}"


def load_slack_config(config_path: Path | None = None) -> dict:
    config = _read_json(config_path or (CONFIG_DIR / "slack.json"))
    workspace_domain = normalize_slack_workspace_domain(
        get_local_env_value(
            "WHIPPER_SLACK_WORKSPACE_DOMAIN",
            "SLACK_WORKSPACE_DOMAIN",
        )
        or str(config.get("workspace_domain", ""))
    )
    return {
        "bot_token": get_local_env_value(
            "WHIPPER_SLACK_BOT_TOKEN",
            "SLACK_BOT_TOKEN",
        )
        or str(config.get("bot_token", "")),
        "app_token": get_local_env_value(
            "WHIPPER_SLACK_APP_TOKEN",
            "SLACK_APP_TOKEN",
        )
        or str(config.get("app_token", "")),
        "bot_user_id": get_local_env_value(
            "WHIPPER_SLACK_BOT_USER_ID",
            "SLACK_BOT_USER_ID",
        )
        or str(config.get("bot_user_id", "")),
        "workspace_domain": workspace_domain,
    }


def load_notion_config(config_path: Path | None = None) -> dict:
    config = _read_json(config_path or (CONFIG_DIR / "notion.json"))
    resolved = dict(config)
    resolved["token"] = get_local_env_value(
        "WHIPPER_NOTION_TOKEN",
        "NOTION_TOKEN",
    ) or str(config.get("token", ""))
    resolved["database_id"] = get_local_env_value(
        "WHIPPER_NOTION_DATABASE_ID",
        "NOTION_DATABASE_ID",
    ) or str(config.get("database_id", ""))
    resolved["video_database_id"] = get_local_env_value(
        "WHIPPER_NOTION_VIDEO_DATABASE_ID",
        "NOTION_VIDEO_DATABASE_ID",
    ) or str(config.get("video_database_id", ""))
    return resolved
