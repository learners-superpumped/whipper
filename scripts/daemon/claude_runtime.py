#!/usr/bin/env python3
"""Helpers for launching whipper's headless agent runtime safely.

The daemon should not inherit arbitrary user MCP servers in production runs.
Whipper's DESIGN v2 expects headless automation to rely on repo-local scripts
and REST APIs, not ambient MCP state from the operator's desktop session.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
CLAUDE_PROVIDER = "claude"
CODEX_PROVIDER = "codex"
DEFAULT_PROVIDER = CLAUDE_PROVIDER
DEFAULT_FALLBACK_PROVIDER = CODEX_PROVIDER
CLAUDE_LIMIT_MARKERS = (
    "you've hit your limit",
    "hit your limit",
    "usage limit",
    "resets 1pm",
)


def normalize_agent_provider(provider: str | None = None) -> str:
    value = (provider or os.getenv("WHIPPER_AGENT_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if not value:
        return DEFAULT_PROVIDER
    return value


def fallback_agent_provider(provider: str | None = None) -> str:
    value = (
        provider
        or os.getenv("WHIPPER_AGENT_FALLBACK_PROVIDER")
        or DEFAULT_FALLBACK_PROVIDER
    )
    return normalize_agent_provider(value)


def output_indicates_claude_limit(output: str) -> bool:
    text = (output or "").lower()
    return any(marker in text for marker in CLAUDE_LIMIT_MARKERS)


def should_retry_with_fallback(
    provider: str,
    output: str,
    *,
    fallback_provider_name: str | None = None,
) -> bool:
    if os.getenv("WHIPPER_DISABLE_AGENT_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return False

    normalized_provider = normalize_agent_provider(provider)
    normalized_fallback = fallback_agent_provider(fallback_provider_name)
    if normalized_provider != CLAUDE_PROVIDER:
        return False
    if normalized_fallback == normalized_provider:
        return False
    return output_indicates_claude_limit(output)


def parse_whipper_headless_prompt(prompt: str) -> tuple[str, str]:
    match = re.match(r"^/whipper:([a-z0-9-]+)(?:\s+(.*))?$", prompt, flags=re.S)
    if not match:
        return "", prompt
    return match.group(1), match.group(2) or ""


def _instruction_paths(skill: str, plugin_root: Path) -> list[Path]:
    paths = [
        plugin_root / "prompts" / "manager.md",
        plugin_root / "prompts" / "executor-base.md",
        plugin_root / "memory" / "profile.json",
        plugin_root / "memory" / "rules.json",
    ]

    command_path = plugin_root / "commands" / f"{skill}.md"
    if command_path.exists():
        paths.insert(0, command_path)

    skill_suffix = skill.removeprefix("whip-")
    executor_path = plugin_root / "prompts" / f"executor-{skill_suffix}.md"
    if skill.startswith("whip-") and executor_path.exists():
        paths.append(executor_path)

    manager_suffix_path = plugin_root / "prompts" / f"manager-{skill_suffix}.md"
    if skill in {"whip-think", "whip-research"} and manager_suffix_path.exists():
        paths.append(manager_suffix_path)

    return paths


def _completion_contract_lines(skill: str) -> list[str]:
    lines = [
        "Current iteration must leave non-empty `iterations/{NN}-execution-plan.md`.",
        "Current iteration must leave non-empty `iterations/{NN}-executor-log.md`.",
        "Current iteration must leave non-empty `iterations/{NN}-manager-eval.md`.",
        "Current iteration must leave non-empty `deliverables/answer.txt` before any success exit.",
    ]

    if skill == "whip-think":
        lines.extend(
            [
                "Save `resources/claude-raw.md`, `resources/gemini-raw.md`, and `resources/chatgpt-raw.md`.",
                "Save `deliverables/종합-분석.md`.",
            ]
        )
    elif skill == "whip-research":
        lines.extend(
            [
                "Save `resources/gemini-research-raw.md`, `resources/chatgpt-research-raw.md`, and `resources/cross-verification.md`.",
                "Save `deliverables/조사-보고서.md`.",
            ]
        )
    elif skill == "whip-learn":
        lines.extend(
            [
                "Save at least one study-note JSON in `deliverables/`.",
                "Save at least one rendered study-note Markdown file in `deliverables/`.",
                "Leave at least one file in `resources/`.",
            ]
        )

    return lines


def build_codex_fallback_prompt(prompt: str, plugin_root: str | Path) -> str:
    root = Path(plugin_root).resolve()
    skill, command_args = parse_whipper_headless_prompt(prompt)
    files = _instruction_paths(skill, root)
    file_list = "\n".join(f"- {path}" for path in files)
    skill_value = skill or "whip"
    completion_contract = "\n".join(
        f"- {line}" for line in _completion_contract_lines(skill_value)
    )

    return f"""You are the fallback Whipper runtime because the Claude CLI hit its usage limit.

Repository root: {root}
Original headless command:
{prompt}

Do not assume Claude slash commands or Claude plugin hooks are available.
Do not stop after planning. Execute the task end-to-end in this one Codex run.

Reference files (open only as needed, do not spend time bulk-reading everything):
{file_list}

Compatibility rules:
1. Use repo-local shell/python scripts and files. Do not rely on external MCP integrations unless the local file instructions explicitly require them.
2. If `.claude/whipper.local.md` does not exist yet, run `scripts/core/setup.sh` with `--skill {skill_value}` and the original command arguments from the headless command above.
3. There is no Claude stop-hook loop here. You must emulate the Manager/Executor loop inline in this single Codex run until the work passes or max_iterations is reached.
4. Use `scripts/core/state.sh` for state updates. Never edit or delete `.claude/whipper.local.md` directly.
5. When Slack context is present, use `scripts/slack/post.sh` for all thread updates.
6. Keep `README.md`, `iterations/`, `deliverables/`, `resources/`, and `deliverables/answer.txt` consistent with the normal Whipper flow.
7. Success completion contract:
{completion_contract}
8. If the task passes, satisfy the completion contract and then run `scripts/core/state.sh delete` before finishing.
9. If the task cannot satisfy the completion contract, write the blocker into the latest manager eval and set state status to `failed` through `scripts/core/state.sh` instead of exiting silently.

Required execution order:
1. Ensure setup/state exists, then read `task_dir`, `iteration`, `skill`, and Slack context.
2. Write `README.md` with command, mapping table, and success criteria.
3. Write `iterations/{{NN}}-execution-plan.md`.
4. Execute the actual task now, not just the plan.
5. Write `iterations/{{NN}}-executor-log.md`.
6. Evaluate results against the success criteria and write `iterations/{{NN}}-manager-eval.md`.
7. If passed, post the result to Slack and run `scripts/core/state.sh delete`.
8. If blocked, post the blocker to Slack and run `scripts/core/state.sh set status failed`.

Skill-specific execution hints:
- `whip`: if the task is closed-form (math/string/count/format), solve it with local shell or python verification and save the final user-facing answer in `deliverables/answer.txt`.
- `whip-think`: use `scripts/think/openai-think.py` and `scripts/think/gemini-think.py`, save all 3 raw outputs including your own `resources/claude-raw.md`, then write `deliverables/종합-분석.md` and `deliverables/answer.txt`.
- `whip-research`: use `scripts/research/openai-research.py` and `scripts/research/gemini-research.py`, cross-check with an official source, then write `resources/cross-verification.md`, `deliverables/조사-보고서.md`, and `deliverables/answer.txt`.
- `whip-learn`: use the existing learn pipeline scripts to generate a study-note JSON, a rendered Markdown note, at least one resource file, and `deliverables/answer.txt`.
- `whip-medical`: answer within the user’s requested scope, include evidence links in the artifacts, and save the exact user-facing answer to `deliverables/answer.txt`.

Start executing immediately.
"""


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


def build_codex_exec_command(
    prompt: str,
    plugin_root: str | Path,
    *,
    permission_mode: str | None = None,
) -> list[str]:
    del permission_mode
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(Path(plugin_root)),
        "--add-dir",
        "/tmp",
        "--add-dir",
        str(Path.home() / ".claude"),
        "--skip-git-repo-check",
    ]
    model_name = os.getenv("WHIPPER_CODEX_MODEL", "").strip()
    if model_name:
        command.extend(["-m", model_name])
    reasoning_effort = os.getenv("WHIPPER_CODEX_REASONING_EFFORT", "low").strip()
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append(build_codex_fallback_prompt(prompt, plugin_root))
    return command


def build_agent_exec_command(
    prompt: str,
    plugin_root: str | Path,
    *,
    provider: str | None = None,
    permission_mode: str | None = None,
) -> list[str]:
    selected = normalize_agent_provider(provider)
    if selected == CODEX_PROVIDER:
        return build_codex_exec_command(
            prompt,
            plugin_root,
            permission_mode=permission_mode,
        )
    return build_claude_print_command(
        prompt,
        plugin_root,
        permission_mode=permission_mode,
    )


def create_output_log(
    *,
    prefix: str = "whipper-runtime-",
    suffix: str = ".log",
) -> tuple[object, Path]:
    handle = tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        prefix=prefix,
        suffix=suffix,
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
