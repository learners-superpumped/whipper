#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daemon.claude_runtime import (
    EMPTY_MCP_CONFIG,
    build_claude_print_command,
    cleanup_output_log,
    create_output_log,
    read_output_tail,
)


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


def test_output_log_helpers_capture_tail_and_cleanup():
    handle, path = create_output_log()
    try:
        handle.write("a" * 700)
        handle.flush()
    finally:
        handle.close()

    tail = read_output_tail(path, max_chars=500)
    assert tail.startswith("...\n")
    assert tail.endswith("a" * 500)

    cleanup_output_log(path)
    assert not path.exists()
