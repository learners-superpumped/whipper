#!/usr/bin/env python3
"""Tests for local settings-based API key loading."""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.core.local_env import export_whipper_aliases, get_local_env_value


def test_get_local_env_value_prefers_process_env():
    old_env = os.environ.copy()
    os.environ["WHIPPER_GEMINI_API_KEY"] = "env-gemini"
    try:
        assert get_local_env_value("WHIPPER_GEMINI_API_KEY", "GEMINI_API_KEY") == "env-gemini"
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_get_local_env_value_reads_settings_file():
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        settings = Path(tmp) / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "env": {
                        "CALLME_OPENAI_API_KEY": "settings-openai",
                        "GEMINI_API_KEY": "settings-gemini",
                    }
                }
            )
        )
        os.environ["WHIPPER_SETTINGS_FILE"] = str(settings)
        os.environ.pop("CALLME_OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        assert get_local_env_value("WHIPPER_OPENAI_API_KEY", "CALLME_OPENAI_API_KEY") == "settings-openai"
        assert get_local_env_value("WHIPPER_GEMINI_API_KEY", "GEMINI_API_KEY") == "settings-gemini"
    os.environ.clear()
    os.environ.update(old_env)


def test_export_whipper_aliases_populates_missing_aliases():
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        settings = Path(tmp) / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "env": {
                        "CALLME_OPENAI_API_KEY": "settings-openai",
                        "GEMINI_API_KEY": "settings-gemini",
                    }
                }
            )
        )
        os.environ["WHIPPER_SETTINGS_FILE"] = str(settings)
        env = export_whipper_aliases({})
        assert env["WHIPPER_OPENAI_API_KEY"] == "settings-openai"
        assert env["WHIPPER_GEMINI_API_KEY"] == "settings-gemini"
    os.environ.clear()
    os.environ.update(old_env)


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
