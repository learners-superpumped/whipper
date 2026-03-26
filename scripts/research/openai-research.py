#!/usr/bin/env python3
"""OpenAI deep research via Responses API with background mode."""
import sys
import os
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.core.local_env import get_local_env_value


def extract_output_text(response) -> str:
    result_parts = []
    sources = []
    for item in getattr(response, "output", []) or []:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type == "output_text":
                result_parts.append(content.text)
                for ann in getattr(content, "annotations", []) or []:
                    if ann.type == "url_citation":
                        sources.append(f"- [{ann.title}]({ann.url})")

    result = "\n".join(result_parts)
    if sources:
        result += "\n\n## Sources\n" + "\n".join(sources)
    return result.strip()


def run_fast_fallback(client, prompt: str) -> str:
    fallback_model = os.getenv("WHIPPER_OPENAI_RESEARCH_FALLBACK_MODEL", "o3").strip() or "o3"
    response = client.responses.create(
        model=fallback_model,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
    )
    result = extract_output_text(response)
    note = (
        "## Fallback Note\n"
        "OpenAI deep research background job did not complete within the operational wait budget, "
        "so a search-grounded synchronous fallback was used.\n\n"
    )
    return note + result if result else note.rstrip()

def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not prompt:
        print("Error: No prompt provided", file=sys.stderr)
        sys.exit(1)

    api_key = get_local_env_value(
        "WHIPPER_OPENAI_API_KEY",
        "CALLME_OPENAI_API_KEY",
    )
    if not api_key:
        print("Error: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("research", {}).get("openai", "o3-deep-research")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    # Start background deep research
    response = client.responses.create(
        model=model_name,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
        background=True,
    )

    # Poll until complete (max 30 min)
    max_wait = 1800
    fallback_wait = int(os.getenv("WHIPPER_RESEARCH_DEEP_WAIT_SECONDS", "180"))
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.responses.retrieve(response.id)
        if status.status == "completed":
            break
        if status.status == "failed":
            print(f"Error: Research failed", file=sys.stderr)
            sys.exit(1)
        if elapsed >= fallback_wait:
            print("⚠️ Deep research slow; using fast OpenAI fallback", file=sys.stderr)
            print(run_fast_fallback(client, prompt))
            return
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    print(extract_output_text(status))

if __name__ == "__main__":
    main()
