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
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.responses.retrieve(response.id)
        if status.status == "completed":
            break
        if status.status == "failed":
            print(f"Error: Research failed", file=sys.stderr)
            sys.exit(1)
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    # Extract result
    result_parts = []
    sources = []
    for item in status.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    result_parts.append(content.text)
                    if hasattr(content, "annotations"):
                        for ann in content.annotations:
                            if ann.type == "url_citation":
                                sources.append(f"- [{ann.title}]({ann.url})")

    result = "\n".join(result_parts)
    if sources:
        result += "\n\n## Sources\n" + "\n".join(sources)

    print(result)

if __name__ == "__main__":
    main()
