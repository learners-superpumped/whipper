#!/usr/bin/env python3
"""Helpers for launching whipper's headless Claude runtime safely.

The daemon should not inherit arbitrary user MCP servers in production runs.
Whipper's DESIGN v2 expects headless automation to rely on repo-local scripts
and REST APIs, not ambient MCP state from the operator's desktop session.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

EMPTY_MCP_CONFIG = '{"mcpServers":{}}'


def build_claude_print_command(
    prompt: str,
    plugin_root: str | Path,
    *,
    permission_mode: str | None = None,
) -> list[str]:
    command = [
        "claude",
        "--plugin-dir",
        str(plugin_root),
        "--strict-mcp-config",
        "--mcp-config",
        EMPTY_MCP_CONFIG,
    ]
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])
    command.extend(["-p", prompt])
    return command


def create_output_log() -> tuple[object, Path]:
    handle = tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        prefix="whipper-claude-",
        suffix=".log",
        delete=False,
    )
    return handle, Path(handle.name)


def read_output_tail(log_path: str | Path, max_chars: int = 500) -> str:
    path = Path(log_path)
    if not path.exists():
        return ""
    text = path.read_text(errors="replace")
    if len(text) <= max_chars:
        return text
    return "...\n" + text[-max_chars:]


def cleanup_output_log(log_path: str | Path) -> None:
    try:
        Path(log_path).unlink()
    except FileNotFoundError:
        pass
