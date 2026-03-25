#!/usr/bin/env python3
"""tests/test_fetch_transcript.py — transcript fetch tests."""
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "learn"))

import fetch_transcript as mod


def test_fetch_transcript_returns_error_when_no_transcript_available():
    class FakeApi:
        def list(self, _video_id):
            raise RuntimeError("blocked")

    with patch.object(mod, "YouTubeTranscriptApi", return_value=FakeApi()):
        result = mod.fetch_transcript("abc123xyz00")

    assert result["success"] is False
    assert "blocked" in result["error"]


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
