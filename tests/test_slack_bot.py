#!/usr/bin/env python3
"""tests/test_slack_bot.py — 데몬 유닛 테스트 (Slack API 미접속)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "daemon"))
from slack_bot import (
    apply_thread_page_env,
    build_slack_url,
    clean_mention,
    detect_skill,
    extract_frontmatter_value,
    parse_thread_lookup_result,
    wait_for_task_dir,
)


def test_detect_skill_youtube():
    assert detect_skill("https://youtube.com/watch?v=abc") == "whip-learn"
    assert detect_skill("youtu.be/abc 요약해줘") == "whip-learn"


def test_detect_skill_research():
    assert detect_skill("/research AI 트렌드") == "whip-research"
    assert detect_skill("/조사 경쟁사") == "whip-research"


def test_detect_skill_think():
    assert detect_skill("/think 이 문제 분석해봐") == "whip-think"


def test_detect_skill_medical():
    assert detect_skill("/medical 두통이 심해") == "whip-medical"


def test_detect_skill_default():
    assert detect_skill("리조트 찾아줘") == "whip"
    assert detect_skill("") == "whip"


def test_clean_mention():
    assert clean_mention("<@U12345> 리조트 찾아줘") == "리조트 찾아줘"
    assert clean_mention("<@U12345>  ") == ""
    assert clean_mention("그냥 텍스트") == "그냥 텍스트"
    assert clean_mention("<@U12345> <@U67890> 둘 다 태그") == "둘 다 태그"


def test_extract_frontmatter_value():
    frontmatter = """---
task_dir: "/tmp/whipper-foo"
status: running
---
"""
    assert extract_frontmatter_value(frontmatter, "task_dir") == "/tmp/whipper-foo"
    assert extract_frontmatter_value(frontmatter, "status") == "running"
    assert extract_frontmatter_value(frontmatter, "missing") == ""


def test_build_slack_url():
    assert (
        build_slack_url("C123", "1774434726.092599")
        == "https://learnerscompany.slack.com/archives/C123/p1774434726092599"
    )


def test_parse_thread_lookup_result():
    parsed = parse_thread_lookup_result("page123\tExisting Task\t4\t진행중")
    assert parsed == {
        "page_id": "page123",
        "name": "Existing Task",
        "iteration": 4,
        "status": "진행중",
    }
    assert parse_thread_lookup_result("NOT_FOUND") is None
    assert parse_thread_lookup_result("") is None


def test_apply_thread_page_env():
    env = apply_thread_page_env(
        {"BASE": "1"},
        {
            "mode": "existing",
            "page_id": "page123",
            "notion_url": "https://www.notion.so/page123",
            "name": "Existing Task",
            "iteration": 4,
            "status": "진행중",
        },
    )
    assert env["BASE"] == "1"
    assert env["WHIPPER_THREAD_PAGE_MODE"] == "existing"
    assert env["WHIPPER_NOTION_PAGE_ID"] == "page123"
    assert env["WHIPPER_NOTION_PAGE_URL"] == "https://www.notion.so/page123"
    assert env["WHIPPER_THREAD_PAGE_NAME"] == "Existing Task"
    assert env["WHIPPER_THREAD_PAGE_ITERATION"] == "4"
    assert env["WHIPPER_THREAD_PAGE_STATUS"] == "진행중"


def test_wait_for_task_dir_matches_expected_thread():
    with tempfile.TemporaryDirectory() as tmpdir:
        task_dir = Path(tmpdir) / "whipper-task"
        (task_dir / "slack_messages").mkdir(parents=True)
        state_file = Path(tmpdir) / "whipper.local.md"
        state_file.write_text(
            f"""---
task_dir: "{task_dir}"
---

[Slack thread: C123/1774434726.092599] /think test
"""
        )

        assert wait_for_task_dir(state_file, "1774434726.092599", timeout_seconds=1) == str(task_dir)
        assert wait_for_task_dir(state_file, "1774439999.000000", timeout_seconds=1) == ""


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
