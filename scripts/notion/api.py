#!/usr/bin/env python3
"""Common Notion API module for Whipper.

Reads token and database_id from config/notion.json.
Provides shared helpers for all Notion scripts.
"""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("FAILED", end="")
    sys.exit(1)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "notion.json"
NOTION_API = "https://api.notion.com/v1/"
NOTION_VERSION = "2022-06-28"


def load_config() -> dict:
    """Load config/notion.json. Returns dict with token, database_id, etc."""
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def get_headers() -> dict | None:
    """Return Notion API headers, or None if token is missing."""
    cfg = load_config()
    token = cfg.get("token")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def get_database_id() -> str | None:
    """Return database_id from config, or None."""
    cfg = load_config()
    return cfg.get("database_id")


def to_uuid(page_id: str) -> str:
    """Convert 32-char hex to UUID format with hyphens. Pass-through if already has hyphens."""
    pid = page_id.replace("-", "")
    if len(pid) == 32:
        return f"{pid[:8]}-{pid[8:12]}-{pid[12:16]}-{pid[16:20]}-{pid[20:]}"
    return page_id


def notion_post(endpoint: str, body: dict) -> requests.Response | None:
    """POST to Notion API. Returns Response or None on auth failure."""
    headers = get_headers()
    if not headers:
        return None
    return requests.post(f"{NOTION_API}{endpoint.lstrip('/')}", headers=headers, json=body)


def notion_patch(endpoint: str, body: dict) -> requests.Response | None:
    """PATCH to Notion API. Returns Response or None on auth failure."""
    headers = get_headers()
    if not headers:
        return None
    return requests.patch(f"{NOTION_API}{endpoint.lstrip('/')}", headers=headers, json=body)


def notion_get(endpoint: str, params: dict = None) -> requests.Response | None:
    """GET from Notion API. Returns Response or None on auth failure."""
    headers = get_headers()
    if not headers:
        return None
    return requests.get(f"{NOTION_API}{endpoint.lstrip('/')}", headers=headers, params=params)
