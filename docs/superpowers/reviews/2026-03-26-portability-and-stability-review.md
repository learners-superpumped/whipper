# 2026-03-26 Portability And Stability Review

## Scope

- Remove tracked machine-specific paths and workspace-specific Slack domains
- Verify `DESIGN.md` against current runtime behavior
- Re-review Slack/Notion/daemon stability risks after the recent fixes

## Verified Alignment

- Manager/Executor loop still uses stop-hook driven iteration with `status: running|failed|passed`
- `whip-think` requires Claude + Gemini + ChatGPT raw outputs and synthesis artifacts
- `whip-research` requires Gemini + ChatGPT deep research raw outputs and cross-verification artifacts
- `whip-learn` uses the migrated `youtube-summarize` style pipeline
- Task runtime storage is `/tmp/whipper-*`, with global indexing in `~/.claude/whipper-logs/index.json`
- Slack and Notion credentials can now come from env vars or ignored local config files
- The tracked launch agent file is now a template, and machine-specific installation is done by `scripts/daemon/install_launch_agent.py`

## Stability Fixes In This Pass

- Follow-up Slack replies now survive daemon restarts by looking up the existing Notion-mapped Slack thread before ignoring a reply
- Workspace-specific Slack URL construction is now driven by runtime config instead of a hardcoded workspace domain
- Tracked docs and examples no longer contain the original machine path or workspace domain
- `tasks/` is now gitignored to avoid leaking local runtime artifacts

## Remaining Non-Critical Risks

- `slack_bot.py` and `dispatch.py` still share similar helper logic; the main functional gaps were fixed, but deeper de-duplication would reduce future drift
- Scheduler follow-ups still run synchronously; a hung follow-up can delay the next scheduled scan until timeout
- The daemon still depends on local Slack/Notion/API credentials being provided out-of-band, by design
