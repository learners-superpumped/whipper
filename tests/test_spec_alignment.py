#!/usr/bin/env python3
"""Prompt/command alignment tests for DESIGN.md v2."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text()


def test_headless_commands_have_no_slack_or_notion_mcp_tools():
    command_files = [
        "commands/whip.md",
        "commands/whip-think.md",
        "commands/whip-research.md",
        "commands/whip-medical.md",
        "commands/whip-learn.md",
        "commands/whip-cancel.md",
        "commands/whip-status.md",
        "commands/whip-todo.md",
    ]
    for rel_path in command_files:
        content = _read(rel_path)
        assert "mcp__claude_ai_Notion__" not in content, rel_path
        assert "mcp__claude_ai_Slack__" not in content, rel_path


def test_think_prompt_requires_parallel_worker_scripts():
    content = _read("prompts/executor-think.md")
    assert 'scripts/think/gemini-think.py' in content
    assert 'scripts/think/openai-think.py' in content
    assert '종합-분석.md' in content
    assert '필수' in content
    assert '축소 실행 금지' in content
    assert _read("prompts/manager-think.md").count("PASS 금지") >= 1


def test_research_prompt_requires_parallel_research_and_cross_verification():
    content = _read("prompts/executor-research.md")
    assert 'scripts/research/gemini-research.py' in content
    assert 'scripts/research/openai-research.py' in content
    assert 'cross-verification.md' in content
    assert '조사-보고서.md' in content
    assert '축소 실행 금지' in content
    assert _read("prompts/manager-research.md").count("PASS 금지") >= 1


def test_learn_prompt_uses_rest_markdown_publish_script():
    content = _read("prompts/executor-learn.md")
    command = _read("commands/whip-learn.md")
    assert 'scripts/notion/publish_markdown.py' in content
    assert 'fetch_transcript.py' in content
    assert 'capture_screenshots.py' in content
    assert 'generate_study_note.py' in content
    assert '--transcript' in content
    assert 'Notion MCP' not in content
    assert 'transcript 폴백' in command


def test_cancel_status_and_todo_commands_use_repo_scripts():
    cancel = _read("commands/whip-cancel.md")
    status = _read("commands/whip-status.md")
    todo = _read("commands/whip-todo.md")
    assert 'scripts/notion/update_status.py' in cancel
    assert 'scripts/notion/list_projects.py' in status
    assert 'scripts/daemon/todo_once.py' in todo


def test_think_and_research_commands_require_external_keys_and_manager_invariants():
    think = _read("commands/whip-think.md")
    research = _read("commands/whip-research.md")
    manager = _read("prompts/manager.md")

    assert "Required API Keys" in think
    assert "Required API Keys" in research
    assert "3개 응답 수신" in think
    assert "2개 raw 결과 수신" in research
    assert "manager-think.md" in think
    assert "manager-research.md" in research
    assert "0.3 — 스킬별 필수 기준" in manager
    assert "4.0단계: 실행 계획 파일 검증" in manager
    assert "README만 읽어도 현재 작업 상태와 최종 결론을 이해할 수 있어야 한다." in manager
    assert "resources/gemini-raw.md" in manager
    assert "resources/chatgpt-research-raw.md" in manager
