#!/usr/bin/env python3
"""Shared whipper Slack/Notion dispatch helpers."""
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
STATE_FILE = Path(os.path.expanduser("~")) / ".claude" / "whipper.local.md"

sys.path.insert(0, str(ROOT_DIR))

from scripts.slack.bridge import SlackBridge
from scripts.core.local_env import export_whipper_aliases
from scripts.core.runtime_config import build_slack_thread_url, load_slack_config
try:
    from .claude_runtime import (
        build_agent_exec_command,
        cleanup_output_log,
        create_output_log,
        fallback_agent_provider,
        normalize_agent_provider,
        read_output_tail,
        should_retry_with_fallback,
    )
    from .run_lock import acquire_run_lock, release_run_lock
except ImportError:
    from claude_runtime import (
        build_agent_exec_command,
        cleanup_output_log,
        create_output_log,
        fallback_agent_provider,
        normalize_agent_provider,
        read_output_tail,
        should_retry_with_fallback,
    )
    from run_lock import acquire_run_lock, release_run_lock

logger = logging.getLogger("whipper-daemon")


def resolve_state_file(env: dict | None = None) -> Path:
    if env:
        candidate = env.get("WHIPPER_STATE_FILE", "").strip()
        if candidate:
            return Path(candidate).expanduser()
    return STATE_FILE


def resolve_final_state(
    final_marker: str | None, returncode: int | None, timed_out: bool
) -> tuple[str, str]:
    if timed_out:
        return "blocked", "timeout"
    if final_marker == "passed":
        return "passed", "passed"
    if final_marker in {"blocked", "failed", "max_iterations"}:
        return "blocked", final_marker
    if returncode == 0:
        return "passed", "exit_0"
    return "blocked", "nonzero_exit"


def notion_status_for(final_state: str) -> str:
    return "완료" if final_state == "passed" else "블락드"


def build_slack_url(channel: str, thread_ts: str) -> str:
    workspace_domain = load_slack_config().get("workspace_domain", "")
    return build_slack_thread_url(workspace_domain, channel, thread_ts)


def build_final_slack_message(final_state: str, reason: str, output: str) -> str:
    if final_state == "passed":
        return "✅ 작업 완료!"

    prefix = {
        "timeout": "⏰ 시간 초과. 후속 확인이 필요합니다.",
        "max_iterations": "🚫 최대 iteration에 도달했습니다. 스레드에 답장 주시면 이어서 진행합니다.",
        "failed": "🚫 작업이 블락되었습니다. 스레드에 추가 지시를 남겨주세요.",
        "blocked": "🚫 작업이 블락되었습니다. 스레드에 추가 지시를 남겨주세요.",
        "nonzero_exit": "❌ 오류로 중단되었습니다. 스레드에 추가 지시를 남겨주세요.",
        "missing_outputs": "🚫 필수 산출물이 비어 있거나 누락되어 완료로 처리하지 않았습니다.",
        "state_not_cleared": "🚫 런타임이 정상 완료 규약을 지키지 못했습니다. state가 정리되지 않았습니다.",
    }.get(reason, "🚫 추가 확인이 필요합니다. 스레드에 지시를 남겨주세요.")

    if not output.strip():
        return prefix
    return f"{prefix}\n```\n{output}\n```"


def extract_frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not match:
        return ""

    value = match.group(1).strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def clear_stale_state_for_thread(state_file: Path, expected_thread_ts: str) -> bool:
    try:
        if not state_file.exists():
            return False
        frontmatter = state_file.read_text()
    except OSError:
        return False

    task_dir = extract_frontmatter_value(frontmatter, "task_dir")
    task_dir_valid = bool(
        task_dir
        and os.path.isdir(task_dir)
        and os.path.isdir(os.path.join(task_dir, "slack_messages"))
    )
    if expected_thread_ts in frontmatter and task_dir_valid:
        return False

    try:
        state_file.unlink()
        logger.warning("Removed stale state file %s for thread %s", state_file, expected_thread_ts)
        return True
    except OSError:
        return False


def parse_thread_lookup_result(raw: str) -> dict | None:
    line = (raw or "").strip()
    if not line or line == "NOT_FOUND":
        return None

    parts = line.split("\t")
    if len(parts) < 4:
        return None

    page_id, name, iteration, status = parts[:4]
    try:
        iteration_value = int(iteration or 0)
    except ValueError:
        iteration_value = 0

    return {
        "page_id": page_id,
        "name": name,
        "iteration": iteration_value,
        "status": status,
    }


def lookup_thread_page(channel: str, thread_ts: str) -> dict | None:
    slack_url = build_slack_url(channel, thread_ts)
    query = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "notion" / "query_thread.py"), slack_url],
        capture_output=True,
        text=True,
        timeout=15,
    )
    existing = parse_thread_lookup_result(query.stdout)
    if not existing:
        return None

    page_id = existing["page_id"]
    return {
        "mode": "existing",
        "page_id": page_id,
        "notion_url": f"https://www.notion.so/{page_id}",
        "name": existing["name"],
        "iteration": existing["iteration"],
        "status": existing["status"],
    }


def determine_thread_page(prompt: str, skill: str, channel: str, thread_ts: str) -> dict:
    existing = lookup_thread_page(channel, thread_ts)
    if existing:
        return existing

    name = prompt.split("]")[-1].strip()[:50] if "]" in prompt else prompt[:50]
    slack_url = build_slack_url(channel, thread_ts)
    create = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "notion" / "create_page.py"),
            "--name",
            name or "Whipper Task",
            "--skill",
            skill,
            "--slack-url",
            slack_url,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    parts = create.stdout.strip().split()
    if len(parts) >= 2 and parts[0] not in ("FAILED", "NO_DB", "NO_TOKEN"):
        page_id, notion_url = parts[0], parts[1]
        logger.info("Notion page created: %s", notion_url)
        return {
            "mode": "new",
            "page_id": page_id,
            "notion_url": notion_url,
            "name": name or "Whipper Task",
            "iteration": 1,
            "status": "진행중",
        }

    if create.stdout.strip():
        logger.warning("Notion page provisioning skipped: %s", create.stdout.strip())
    if create.stderr.strip():
        logger.warning("Notion page provisioning stderr: %s", create.stderr.strip())
    return {
        "mode": "unknown",
        "page_id": "",
        "notion_url": "",
        "name": "",
        "iteration": 0,
        "status": "",
    }


def apply_thread_page_env(env: dict, thread_page: dict) -> dict:
    applied = dict(env)
    applied["WHIPPER_THREAD_PAGE_MODE"] = thread_page.get("mode", "unknown")
    applied["WHIPPER_NOTION_PAGE_ID"] = thread_page.get("page_id", "")
    applied["WHIPPER_NOTION_PAGE_URL"] = thread_page.get("notion_url", "")
    applied["WHIPPER_THREAD_PAGE_NAME"] = thread_page.get("name", "")
    applied["WHIPPER_THREAD_PAGE_ITERATION"] = str(thread_page.get("iteration", 0))
    applied["WHIPPER_THREAD_PAGE_STATUS"] = thread_page.get("status", "")
    return applied


def wait_for_task_dir(state_file: Path, expected_thread_ts: str, timeout_seconds: int = 30) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if not state_file.exists():
                time.sleep(1)
                continue

            frontmatter = state_file.read_text()
            if expected_thread_ts not in frontmatter:
                time.sleep(1)
                continue

            task_dir = extract_frontmatter_value(frontmatter, "task_dir")
            if task_dir and os.path.isdir(task_dir) and os.path.isdir(os.path.join(task_dir, "slack_messages")):
                return task_dir
        except OSError:
            pass

        time.sleep(1)

    return ""


def detect_latest_iteration(task_dir: str) -> int:
    iterations_dir = Path(task_dir) / "iterations"
    latest = 0
    if not iterations_dir.is_dir():
        return latest

    for path in iterations_dir.glob("*.md"):
        match = re.match(r"^(\d+)-", path.name)
        if not match:
            continue
        latest = max(latest, int(match.group(1)))
    return latest


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _iteration_file(task_dir: str, iteration: int, suffix: str) -> Path:
    iterations_dir = Path(task_dir) / "iterations"
    padded = iterations_dir / f"{iteration:02d}-{suffix}"
    if _nonempty_file(padded):
        return padded
    plain = iterations_dir / f"{iteration}-{suffix}"
    return plain


def collect_missing_outputs(task_dir: str, skill: str) -> list[str]:
    td = Path(task_dir)
    missing: list[str] = []
    readme_path = td / "README.md"
    readme_text = readme_path.read_text() if _nonempty_file(readme_path) else ""

    if not _nonempty_file(readme_path):
        missing.append("README.md")

    latest_iteration = detect_latest_iteration(task_dir)
    if latest_iteration <= 0:
        missing.extend(
            [
                "iterations/{NN}-execution-plan.md",
                "iterations/{NN}-executor-log.md",
                "iterations/{NN}-manager-eval.md",
            ]
        )
    else:
        for suffix in ("execution-plan.md", "executor-log.md", "manager-eval.md"):
            path = _iteration_file(task_dir, latest_iteration, suffix)
            if not _nonempty_file(path):
                missing.append(f"iterations/{latest_iteration:02d}-{suffix}")

    answer_required = skill != "whip" or "answer.txt" in readme_text
    if answer_required and not _nonempty_file(td / "deliverables" / "answer.txt"):
        missing.append("deliverables/answer.txt")

    if skill == "whip-think":
        for rel in (
            "resources/claude-raw.md",
            "resources/gemini-raw.md",
            "resources/chatgpt-raw.md",
            "deliverables/종합-분석.md",
        ):
            if not _nonempty_file(td / rel):
                missing.append(rel)
    elif skill == "whip-research":
        for rel in (
            "resources/gemini-research-raw.md",
            "resources/chatgpt-research-raw.md",
            "resources/cross-verification.md",
            "deliverables/조사-보고서.md",
        ):
            if not _nonempty_file(td / rel):
                missing.append(rel)
    elif skill == "whip-learn":
        deliverables_dir = td / "deliverables"
        resources_dir = td / "resources"
        json_files = [
            path for path in deliverables_dir.glob("*.json") if _nonempty_file(path)
        ]
        md_files = [
            path for path in deliverables_dir.glob("*.md") if _nonempty_file(path)
        ]
        resource_files = [
            path for path in resources_dir.glob("*") if _nonempty_file(path)
        ]
        if not json_files:
            missing.append("deliverables/*.json")
        if not md_files:
            missing.append("deliverables/*.md")
        if not resource_files:
            missing.append("resources/*")

    return missing


def _cleanup_state_file(runtime_env: dict, state_file: Path) -> None:
    subprocess.run(
        [str(SCRIPTS_DIR / "core" / "state.sh"), "delete"],
        cwd=str(ROOT_DIR),
        env={**runtime_env, "WHIPPER_STATE_FILE": str(state_file)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )


def enforce_completion_contract(
    task_dir: str,
    skill: str,
    final_state: str,
    final_reason: str,
    *,
    state_file: Path | None = None,
) -> tuple[str, str, list[str], bool]:
    if not task_dir or not os.path.isdir(task_dir):
        return final_state, final_reason, [], False

    state_file = state_file or STATE_FILE
    missing_outputs = collect_missing_outputs(task_dir, skill)
    state_still_present = state_file.exists()

    if final_state == "passed" and state_still_present and not missing_outputs:
        return "passed", "state_autocleared", [], True
    if final_state == "passed" and state_still_present:
        return "blocked", "state_not_cleared", missing_outputs, False
    if final_state == "passed" and missing_outputs:
        return "blocked", "missing_outputs", missing_outputs, False
    return final_state, final_reason, missing_outputs, False


def append_missing_outputs(output: str, missing_outputs: list[str]) -> str:
    if not missing_outputs:
        return output

    summary = "필수 산출물 누락:\n" + "\n".join(f"- {path}" for path in missing_outputs)
    if not output.strip():
        return summary
    return f"{summary}\n\n{output}"


def run_dispatch(slack_client, bridge: SlackBridge, prompt: str, skill: str, channel: str, thread_ts: str):
    lock_handle = None
    output_handle = None
    output_path = None
    try:
        lock_handle = acquire_run_lock(blocking=False)
        if lock_handle is None:
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="⏸️ 다른 작업이 실행 중이라 대기열에 넣었습니다.",
            )
            lock_handle = acquire_run_lock(blocking=True)

        logger.info(
            "Dispatching skill=%s channel=%s thread=%s prompt=%s",
            skill,
            channel,
            thread_ts,
            prompt[:120],
        )
        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"🔥 작업 시작... (/{skill})",
        )

        thread_page = determine_thread_page(prompt, skill, channel, thread_ts)
        full_prompt = f"/whipper:{skill} {prompt}"
        runtime_env = export_whipper_aliases(os.environ.copy())
        runtime_env["CLAUDE_PLUGIN_ROOT"] = str(ROOT_DIR)
        runtime_env = apply_thread_page_env(runtime_env, thread_page)
        state_file = resolve_state_file(runtime_env)
        clear_stale_state_for_thread(state_file, thread_ts)
        notion_page_id = thread_page.get("page_id", "")
        bridge_started = False
        primary_provider = normalize_agent_provider()
        secondary_provider = fallback_agent_provider()

        def run_provider(provider: str, existing_task_dir: str = "") -> dict:
            nonlocal output_handle, output_path, bridge_started

            if output_handle is not None:
                output_handle.close()
                output_handle = None
            if output_path is not None:
                cleanup_output_log(output_path)
                output_path = None

            output_handle, output_path = create_output_log(prefix=f"whipper-{provider}-")
            process = subprocess.Popen(
                build_agent_exec_command(
                    full_prompt,
                    ROOT_DIR,
                    provider=provider,
                    permission_mode="bypassPermissions",
                ),
                stdout=output_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                cwd=os.path.expanduser("~"),
                env=runtime_env,
            )

            task_dir_found = existing_task_dir
            if not task_dir_found:
                task_dir_found = wait_for_task_dir(state_file, thread_ts, timeout_seconds=30)
            if task_dir_found:
                if not bridge_started:
                    bridge.watch(task_dir_found, channel, thread_ts)
                    logger.info("Bridge started for: %s", task_dir_found)
                    bridge_started = True
                if thread_page.get("page_id"):
                    Path(task_dir_found, ".notion_page_id").write_text(thread_page["page_id"])
            else:
                logger.warning("No task_dir with slack_messages/ found after 30s")

            timeout = 1800
            start = time.time()
            last_ping = start
            final_status_detected_at = None
            final_status_marker = ""
            timed_out = False
            while process.poll() is None:
                elapsed = time.time() - start
                if elapsed > timeout:
                    timed_out = True
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except Exception:
                        pass
                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text=f"⏰ 시간 초과 ({timeout // 60}분).",
                    )
                    break

                if task_dir_found and not state_file.exists() and final_status_detected_at is None:
                    marker_path = Path(task_dir_found) / ".final_status"
                    if marker_path.exists():
                        final_status_marker = marker_path.read_text().strip()
                    else:
                        final_status_marker = "passed"
                    final_status_detected_at = time.time()
                    wait_seconds = 60 if final_status_marker == "passed" else 10
                    logger.info(
                        "Final state detected from %s: %s. Waiting %ss before forcing exit.",
                        provider,
                        final_status_marker,
                        wait_seconds,
                    )

                if final_status_detected_at:
                    wait_seconds = 60 if final_status_marker == "passed" else 10
                    if time.time() - final_status_detected_at > wait_seconds:
                        logger.info(
                            "Force-killing %s after final state=%s",
                            provider,
                            final_status_marker or "unknown",
                        )
                        process.kill()
                        try:
                            process.wait(timeout=10)
                        except Exception:
                            pass
                        break

                if time.time() - last_ping > 300 and not final_status_detected_at:
                    mins = int(elapsed // 60)
                    slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text=f"⏳ 작업 진행중... ({mins}분 경과)",
                    )
                    last_ping = time.time()
                time.sleep(5)

            if output_handle is not None:
                output_handle.flush()
                output_handle.close()
                output_handle = None
            output = read_output_tail(output_path) if output_path else ""
            final_state, final_reason = resolve_final_state(
                final_status_marker or None, process.returncode, timed_out
            )
            retry_with_fallback = should_retry_with_fallback(
                provider,
                output,
                fallback_provider_name=secondary_provider,
            )
            return {
                "provider": provider,
                "task_dir_found": task_dir_found,
                "output": output,
                "final_state": final_state,
                "final_reason": final_reason,
                "retry_with_fallback": retry_with_fallback,
            }

        result = run_provider(primary_provider)
        if result["retry_with_fallback"]:
            logger.warning(
                "Primary provider %s hit its limit. Retrying with %s.",
                primary_provider,
                secondary_provider,
            )
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"⚠️ {primary_provider} 한도 초과로 {secondary_provider}로 자동 재시도합니다.",
            )
            result = run_provider(
                secondary_provider,
                existing_task_dir=result["task_dir_found"],
            )

        task_dir_found = result["task_dir_found"]
        output = result["output"]
        final_state = result["final_state"]
        final_reason = result["final_reason"]
        final_state, final_reason, missing_outputs, should_cleanup_state = enforce_completion_contract(
            task_dir_found,
            skill,
            final_state,
            final_reason,
            state_file=state_file,
        )
        output = append_missing_outputs(output, missing_outputs)

        if should_cleanup_state and state_file.exists():
            _cleanup_state_file(runtime_env, state_file)
        elif final_state != "passed" and state_file.exists():
            _cleanup_state_file(runtime_env, state_file)

        if notion_page_id and task_dir_found and os.path.isdir(task_dir_found):
            try:
                latest_iteration = detect_latest_iteration(task_dir_found)
                upload_args = [
                    sys.executable,
                    str(SCRIPTS_DIR / "notion" / "upload_task.py"),
                    notion_page_id,
                    task_dir_found,
                    "--status",
                    notion_status_for(final_state),
                ]
                if latest_iteration > 0:
                    upload_args.extend(["--set-iteration", str(latest_iteration)])
                subprocess.run(
                    upload_args,
                    timeout=300,
                    check=True,
                )
                logger.info(
                    "Notion upload complete: %s from %s (status=%s)",
                    notion_page_id,
                    task_dir_found,
                    notion_status_for(final_state),
                )
            except Exception as e:
                logger.error("Notion upload failed: %s", e)
            if final_state == "passed":
                shutil.rmtree(task_dir_found, ignore_errors=True)
                logger.info("Cleaned up: %s", task_dir_found)
            else:
                logger.info("Keeping blocked task_dir for inspection: %s", task_dir_found)

        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=build_final_slack_message(final_state, final_reason, output),
        )
    except Exception as e:
        logger.error("spawn error: %s", e)
        slack_client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=f"❌ 오류: {e}"
        )
    finally:
        if output_handle is not None:
            output_handle.close()
        if output_path is not None:
            cleanup_output_log(output_path)
        release_run_lock(lock_handle)


def spawn_dispatch(slack_client, bridge: SlackBridge, prompt: str, skill: str, channel: str, thread_ts: str):
    threading.Thread(
        target=run_dispatch,
        args=(slack_client, bridge, prompt, skill, channel, thread_ts),
        daemon=True,
    ).start()
