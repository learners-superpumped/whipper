#!/usr/bin/env python3
"""tests/test_dispatch_completion.py — dispatch completion contract tests."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "daemon"))

import dispatch


def _write(path: Path, content: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_collect_missing_outputs_for_think_requires_skill_files():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        _write(task_dir / "README.md")
        _write(task_dir / "iterations" / "01-execution-plan.md")
        _write(task_dir / "iterations" / "01-executor-log.md")
        _write(task_dir / "iterations" / "01-manager-eval.md")
        _write(task_dir / "deliverables" / "answer.txt", "225")
        _write(task_dir / "resources" / "claude-raw.md")

        missing = dispatch.collect_missing_outputs(str(task_dir), "whip-think")

    assert "resources/gemini-raw.md" in missing
    assert "resources/chatgpt-raw.md" in missing
    assert "deliverables/종합-분석.md" in missing


def test_clear_stale_state_for_other_thread():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "whipper.local.md"
        state_file.write_text(
            '---\n'
            'task_dir: "/tmp/other-task"\n'
            '---\n'
            '[Slack thread: C0TEST/111.222] old prompt\n'
        )

        removed = dispatch.clear_stale_state_for_thread(state_file, "333.444")

    assert removed is True
    assert not state_file.exists()


def test_collect_missing_outputs_for_learn_requires_json_md_and_resources():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        _write(task_dir / "README.md")
        _write(task_dir / "iterations" / "01-execution-plan.md")
        _write(task_dir / "iterations" / "01-executor-log.md")
        _write(task_dir / "iterations" / "01-manager-eval.md")
        _write(task_dir / "deliverables" / "answer.txt", "summary")

        missing = dispatch.collect_missing_outputs(str(task_dir), "whip-learn")

    assert "deliverables/*.json" in missing
    assert "deliverables/*.md" in missing
    assert "resources/*" in missing


def test_enforce_completion_contract_blocks_pass_when_state_not_cleared():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp) / "task"
        _write(task_dir / "README.md")
        _write(task_dir / "iterations" / "01-execution-plan.md")
        _write(task_dir / "iterations" / "01-executor-log.md")
        _write(task_dir / "iterations" / "01-manager-eval.md")
        _write(task_dir / "deliverables" / "answer.txt", "4")
        state_file = Path(tmp) / "whipper.local.md"
        state_file.write_text("still here")

        with patch.object(dispatch, "STATE_FILE", state_file):
            final_state, final_reason, missing, autoclean = dispatch.enforce_completion_contract(
                str(task_dir),
                "whip",
                "passed",
                "exit_0",
            )

    assert final_state == "passed"
    assert final_reason == "state_autocleared"
    assert missing == []
    assert autoclean is True


def test_enforce_completion_contract_blocks_pass_when_outputs_missing():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp) / "task"
        _write(task_dir / "README.md")
        _write(task_dir / "iterations" / "01-execution-plan.md")
        state_file = Path(tmp) / "missing-state.md"

        with patch.object(dispatch, "STATE_FILE", state_file):
            final_state, final_reason, missing, autoclean = dispatch.enforce_completion_contract(
                str(task_dir),
                "whip-medical",
                "passed",
                "exit_0",
            )

    assert final_state == "blocked"
    assert final_reason == "missing_outputs"
    assert "deliverables/answer.txt" in missing
    assert "iterations/01-executor-log.md" in missing
    assert "iterations/01-manager-eval.md" in missing
    assert autoclean is False


def test_append_missing_outputs_includes_summary():
    text = dispatch.append_missing_outputs("tail", ["deliverables/answer.txt"])
    assert "필수 산출물 누락" in text
    assert "deliverables/answer.txt" in text
    assert text.endswith("tail")


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
