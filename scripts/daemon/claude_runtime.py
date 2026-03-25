#!/usr/bin/env python3
"""Helpers for launching whipper's headless Claude runtime safely.

The daemon should not inherit arbitrary user MCP servers in production runs.
Whipper's DESIGN v2 expects headless automation to rely on repo-local scripts
and REST APIs, not ambient MCP state from the operator's desktop session.
"""

from __future__ import annotations

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
