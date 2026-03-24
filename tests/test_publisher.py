#!/usr/bin/env python3
"""tests/test_publisher.py — Notion publisher 단위 테스트."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "notion"))
from publisher import format_for_notion, cleanup_task_dir


def _make_task_dir():
    d = tempfile.mkdtemp(prefix="/tmp/whipper-test-")
    os.makedirs(f"{d}/iterations", exist_ok=True)
    os.makedirs(f"{d}/deliverables", exist_ok=True)
    os.makedirs(f"{d}/resources", exist_ok=True)
    with open(f"{d}/README.md", "w") as f:
        f.write("# 테스트\n## 성공기준\n1. 항목A")
    with open(f"{d}/deliverables/report.md", "w") as f:
        f.write("보고서 내용")
    with open(f"{d}/iterations/01-executor-log.md", "w") as f:
        f.write("검색 수행")
    with open(f"{d}/iterations/01-manager-eval.md", "w") as f:
        f.write("PASS")
    return d


def test_format_basic():
    d = _make_task_dir()
    result = format_for_notion(d)
    assert "성공기준" in result
    assert "보고서 내용" in result
    assert "검색 수행" in result
    assert "PASS" in result
    cleanup_task_dir(d)


def test_format_with_media():
    d = _make_task_dir()
    urls = {"photo.jpg": "https://files.catbox.moe/abc.jpg"}
    result = format_for_notion(d, urls)
    assert "![photo.jpg]" in result
    cleanup_task_dir(d)


def test_format_without_media():
    d = _make_task_dir()
    result = format_for_notion(d)
    assert "첨부" not in result
    cleanup_task_dir(d)


def test_cleanup():
    d = _make_task_dir()
    assert os.path.isdir(d)
    cleanup_task_dir(d)
    assert not os.path.isdir(d)


def test_cleanup_safety():
    """non-/tmp/whipper- 경로는 삭제하지 않음."""
    cleanup_task_dir("/Users/nevermind/important")
    cleanup_task_dir("/tmp/other-stuff")
    assert True


def test_empty_task_dir():
    d = tempfile.mkdtemp(prefix="/tmp/whipper-test-")
    result = format_for_notion(d)
    assert result == ""
    cleanup_task_dir(d)


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
