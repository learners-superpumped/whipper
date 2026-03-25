#!/usr/bin/env python3
"""tests/test_upload_task.py — upload iteration compatibility tests."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "notion"))

from upload_task import update_page_properties, upload_all, upload_iteration


def test_upload_iteration_accepts_zero_padded_and_plain_prefixes():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        iterations = task_dir / "iterations"
        iterations.mkdir()
        (iterations / "01-manager-eval.md").write_text("padded")
        (iterations / "1-executor-log.md").write_text("plain")

        uploaded = []

        def fake_upload_file(_page_id, heading, content):
            uploaded.append((heading, content))

        with patch("upload_task.upload_file", side_effect=fake_upload_file):
            upload_iteration("page-id", str(task_dir), 1)

        assert ("📝 Iteration 1: 01-manager-eval", "padded") in uploaded
        assert ("📝 Iteration 1: 1-executor-log", "plain") in uploaded
        assert len(uploaded) == 2


def test_upload_all_includes_resources_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        (task_dir / "deliverables").mkdir()
        (task_dir / "resources").mkdir()
        (task_dir / "deliverables" / "answer.txt").write_text("done")
        (task_dir / "resources" / "cross-verification.md").write_text("checked")

        uploaded = []

        def fake_upload_file(_page_id, heading, content):
            uploaded.append((heading, content))

        with patch("upload_task.upload_file", side_effect=fake_upload_file):
            upload_all("page-id", str(task_dir))

        assert ("📦 결과물: answer.txt", "done") in uploaded
        assert ("🔎 자료: cross-verification.md", "checked") in uploaded


def test_update_page_properties_sets_status_and_iteration():
    patched = []

    class FakeResp:
        status_code = 200

    def fake_patch(endpoint, body):
        patched.append((endpoint, body))
        return FakeResp()

    with patch("upload_task.notion_patch", side_effect=fake_patch):
        update_page_properties("123456781234123412341234567890ab", status="완료", iteration=3)

    assert patched == [
        (
            "pages/12345678-1234-1234-1234-1234567890ab",
            {
                "properties": {
                    "Status": {"select": {"name": "완료"}},
                    "Iteration": {"number": 3},
                }
            },
        )
    ]


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
