#!/usr/bin/env python3
"""tests/test_slack_bot.py — 데몬 유닛 테스트 (Slack API 미접속)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "daemon"))
from slack_bot import detect_skill, clean_mention


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
