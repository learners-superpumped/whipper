#!/usr/bin/env python3
"""tests/test_upload_task.py — upload iteration compatibility tests."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "notion"))

from upload_task import clear_page_children, infer_final_summary, update_page_properties, upload_all, upload_iteration


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


def test_upload_all_includes_resources_even_when_not_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        (task_dir / "deliverables").mkdir()
        (task_dir / "resources").mkdir()
        (task_dir / "deliverables" / "answer.txt").write_text("done")
        (task_dir / "resources" / "cross-verification.md").write_text("checked")
        (task_dir / "resources" / "diagram.png").write_bytes(b"\x89PNG\r\n")

        uploaded = []

        def fake_upload_file(_page_id, heading, content):
            uploaded.append((heading, content))

        with patch("upload_task.upload_file", side_effect=fake_upload_file), patch(
            "upload_task.clear_page_children"
        ):
            upload_all("page-id", str(task_dir))

        assert ("📦 결과물: answer.txt", "done") in uploaded
        assert ("🔎 자료: cross-verification.md", "checked") in uploaded
        assert any(
            heading == "🔎 자료: diagram.png" and "바이너리 파일: diagram.png" in content
            for heading, content in uploaded
        )


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


def test_infer_final_summary_uses_status_and_answer():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp)
        (task_dir / "deliverables").mkdir()
        (task_dir / "iterations").mkdir()
        (task_dir / "deliverables" / "answer.txt").write_text("225")
        (task_dir / "iterations" / "01-manager-eval.md").write_text("PASS")
        summary = infer_final_summary(str(task_dir), status="완료")
        assert "상태: 완료" in summary
        assert "최종 답변: 225" in summary
        assert "01-manager-eval.md" in summary
        assert "## 최종 상태 요약" not in summary


def test_clear_page_children_deletes_existing_blocks():
    deleted = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"id": "block-1"},
                    {"id": "block-2"},
                ],
                "has_more": False,
            }

    with patch("upload_task.notion_get", return_value=FakeResp()), patch(
        "upload_task.notion_delete",
        side_effect=lambda endpoint: (deleted.append(endpoint), FakeResp())[1],
    ):
        clear_page_children("123456781234123412341234567890ab")

    assert deleted == [
        "blocks/block-1",
        "blocks/block-2",
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
