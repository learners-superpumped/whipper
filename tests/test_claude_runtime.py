#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daemon.claude_runtime import (
    CODEX_PROVIDER,
    CLAUDE_PROVIDER,
    EMPTY_MCP_CONFIG,
    build_agent_exec_command,
    build_claude_print_command,
    build_codex_exec_command,
    cleanup_output_log,
    create_output_log,
    read_output_tail,
    should_retry_with_fallback,
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


def test_build_codex_exec_command_wraps_whipper_prompt_for_repo_runtime():
    command = build_codex_exec_command("/whipper:whip-think 15의 제곱은? 답만", ROOT)

    assert command[:11] == [
        "codex",
        "exec",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(ROOT),
        "--add-dir",
        "/tmp",
        "--add-dir",
        str(Path.home() / ".claude"),
        "--skip-git-repo-check",
    ]
    assert command[11] == "-c"
    assert command[12] == 'model_reasoning_effort="low"'
    prompt = command[-1]
    assert "fallback Whipper runtime" in prompt
    assert str(ROOT / "commands" / "whip-think.md") in prompt
    assert str(ROOT / "prompts" / "manager.md") in prompt
    assert str(ROOT / "prompts" / "executor-think.md") in prompt
    assert "scripts/core/setup.sh" in prompt
    assert "scripts/core/state.sh" in prompt
    assert "iterations/{NN}-manager-eval.md" in prompt
    assert "deliverables/종합-분석.md" in prompt


def test_build_agent_exec_command_defaults_to_claude():
    command = build_agent_exec_command(
        "/whipper:whip smoke",
        ROOT,
        provider=CLAUDE_PROVIDER,
        permission_mode="bypassPermissions",
    )
    assert command[0] == "claude"


def test_should_retry_with_fallback_only_on_claude_limit():
    assert should_retry_with_fallback(
        CLAUDE_PROVIDER,
        "You've hit your limit · resets 1pm (Asia/Seoul)",
        fallback_provider_name=CODEX_PROVIDER,
    )
    assert not should_retry_with_fallback(
        CLAUDE_PROVIDER,
        "some other nonzero error",
        fallback_provider_name=CODEX_PROVIDER,
    )
    assert not should_retry_with_fallback(
        CODEX_PROVIDER,
        "You've hit your limit · resets 1pm (Asia/Seoul)",
        fallback_provider_name=CODEX_PROVIDER,
    )


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


if __name__ == "__main__":
    passed = failed = 0
    for name in sorted(
        [n for n in dir() if n.startswith("test_") and callable(globals()[n])]
    ):
        try:
            globals()[name]()
            print(f"✅ {name}")
            passed += 1
        except Exception as exc:
            print(f"❌ {name}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
