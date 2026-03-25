# Whipper

Whipper is a Claude Code plugin that runs a Manager/Executor loop, mirrors work into Slack threads, and logs task progress into Notion.

## What Is Tracked

- Prompt, daemon, scheduler, and Notion integration code
- Example configuration files in `config/*.example`
- Portable launch agent template in `scripts/daemon/com.whipper.daemon.plist`

## What Is Not Tracked

- `config/slack.json`
- `config/notion.json`
- `.claude/`
- `tasks/`
- API keys in your shell or `~/.claude/settings.json`

## Required Local Configuration

You can configure Whipper with environment variables, ignored local config files, or both.

### Slack

Set these env vars or place them in `config/slack.json`:

- `WHIPPER_SLACK_WORKSPACE_DOMAIN`
- `WHIPPER_SLACK_BOT_TOKEN`
- `WHIPPER_SLACK_APP_TOKEN`
- `WHIPPER_SLACK_BOT_USER_ID`

See `config/slack.json.example`.

### Notion

Set these env vars or place them in `config/notion.json`:

- `WHIPPER_NOTION_TOKEN`
- `WHIPPER_NOTION_DATABASE_ID`
- `WHIPPER_NOTION_VIDEO_DATABASE_ID`

See `config/notion.json.example`.

### LLM API Keys

Whipper resolves keys in this order:

1. Direct env vars such as `WHIPPER_OPENAI_API_KEY` and `WHIPPER_GEMINI_API_KEY`
2. Fallback env vars such as `CALLME_OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`
3. `~/.claude/settings.json` `env` entries

The mapping is defined in `config/api-keys.json`.

## Install

1. Clone the repo to any path.
2. Fill local Slack/Notion config or export the env vars above.
3. Install Python deps used by the daemon.
4. Install the launch agent for your current machine:

```bash
python3 scripts/daemon/install_launch_agent.py --reload
```

This renders the tracked template into `~/Library/LaunchAgents/com.whipper.daemon.plist` with your current Python path, repo path, and `PATH`.

## Verify

```bash
python3 tests/test_slack_bot.py
python3 tests/test_scheduler.py
python3 tests/test_upload_task.py
python3 tests/test_spec_alignment.py
bash tests/test_core.sh
```

## Design

The primary spec is `DESIGN.md`. Historical implementation notes live under `docs/superpowers/`.
