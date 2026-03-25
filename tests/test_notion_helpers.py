#!/usr/bin/env python3
"""Unit tests for newly added Notion helper scripts."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "notion"))

import list_projects
import publish_markdown


def test_list_projects_parses_rows():
    fake_response = {
        "results": [
            {
                "id": "12345678-1234-1234-1234-1234567890ab",
                "created_time": "2026-03-26T00:00:00.000Z",
                "properties": {
                    "Name": {"title": [{"plain_text": "Task A"}]},
                    "Status": {"select": {"name": "완료"}},
                    "Skill": {"select": {"name": "whip-think"}},
                    "Slack Thread": {"url": "https://example.slack.com/archives/C123/p1"},
                },
            }
        ]
    }

    class FakeResp:
        status_code = 200

        def json(self):
            return fake_response

    with patch.object(list_projects, "get_database_id", return_value="db123"):
        with patch.object(list_projects, "notion_post", return_value=FakeResp()):
            rows = list_projects.list_projects(limit=5)

    assert rows == [
        {
            "page_id": "123456781234123412341234567890ab",
            "name": "Task A",
            "status": "완료",
            "skill": "whip-think",
            "created": "2026-03-26T00:00:00.000Z",
            "slack_thread": "https://example.slack.com/archives/C123/p1",
        }
    ]


def test_publish_markdown_appends_youtube_url_and_markdown_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        md_path = Path(tmp) / "note.md"
        md_path.write_text("# Title\n\n- Bullet")
        calls = []

        class FakeResp:
            status_code = 200

        def fake_patch(endpoint, body):
            calls.append((endpoint, body))
            return FakeResp()

        with patch.object(publish_markdown, "notion_patch", side_effect=fake_patch):
            result = publish_markdown.publish_markdown(
                "123456781234123412341234567890ab",
                str(md_path),
                "https://www.youtube.com/watch?v=abc123",
            )

    assert result == "OK"
    assert calls
    children = calls[0][1]["children"]
    assert children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "https://www.youtube.com/watch?v=abc123"
    assert any(block["type"] == "heading_1" for block in children)
    assert any(block["type"] == "bulleted_list_item" for block in children)
