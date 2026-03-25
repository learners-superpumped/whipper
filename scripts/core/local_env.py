#!/usr/bin/env python3
"""Helpers for loading local API keys from ~/.claude/settings.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _settings_path() -> Path:
    return Path(
        os.environ.get("WHIPPER_SETTINGS_FILE", "~/.claude/settings.json")
    ).expanduser()


def load_settings_env() -> dict[str, str]:
    path = _settings_path()
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}

    env = data.get("env", {}) if isinstance(data, dict) else {}
    if not isinstance(env, dict):
        return {}

    return {str(key): str(value) for key, value in env.items() if value}


def get_local_env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value

    settings_env = load_settings_env()
    for name in names:
        value = settings_env.get(name)
        if value:
            return value
    return ""


def export_whipper_aliases(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)

    if not env.get("WHIPPER_OPENAI_API_KEY"):
        openai_key = get_local_env_value(
            "WHIPPER_OPENAI_API_KEY",
            "CALLME_OPENAI_API_KEY",
        )
        if openai_key:
            env["WHIPPER_OPENAI_API_KEY"] = openai_key

    if not env.get("WHIPPER_GEMINI_API_KEY"):
        gemini_key = get_local_env_value(
            "WHIPPER_GEMINI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        )
        if gemini_key:
            env["WHIPPER_GEMINI_API_KEY"] = gemini_key

    return env
