#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daemon.claude_runtime import EMPTY_MCP_CONFIG, build_claude_print_command


def test_build_claude_print_command_is_plugin_scoped_and_mcp_isolated():
    command = build_claude_print_command(
        "/whipper:whip smoke",
        ROOT,
        permission_mode="bypassPermissions",
    )

    assert command[:6] == [
        "claude",
        "--plugin-dir",
        str(ROOT),
        "--strict-mcp-config",
        "--mcp-config",
        EMPTY_MCP_CONFIG,
    ]
    assert command[6:8] == ["--permission-mode", "bypassPermissions"]
    assert command[-2:] == ["-p", "/whipper:whip smoke"]


def test_prompt_instructions_cover_closed_form_validation():
    manager = (ROOT / "prompts" / "manager.md").read_text()
    executor = (ROOT / "prompts" / "executor-base.md").read_text()

    assert "닫힌형 작업 재검증" in manager
    assert "python3" in manager
    assert "닫힌형 작업 예외" in executor
    assert "문장 끝의 `만`" in executor
