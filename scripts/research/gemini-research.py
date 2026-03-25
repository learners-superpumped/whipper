#!/usr/bin/env python3
"""Gemini deep research via Interactions API. Async polling."""
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

    api_key = get_local_env_value("WHIPPER_GEMINI_API_KEY", "GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("research", {}).get("gemini", "deep-research-pro-preview-12-2025")

    from google import genai

    client = genai.Client(api_key=api_key)

    # Start deep research interaction
    interaction = client.interactions.create(
        agent=model_name,
        user_message=prompt,
        background=True,
        store=True,
    )

    # Poll until complete (max 30 min)
    max_wait = 1800
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.interactions.get(interaction.id)
        if status.status == "COMPLETED":
            break
        if status.status == "FAILED":
            print(f"Error: Research failed — {status.error}", file=sys.stderr)
            sys.exit(1)
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    # Extract result
    result = status.response.text if hasattr(status.response, "text") else str(status.response)

    # Extract sources
    if hasattr(status, "grounding_metadata") and status.grounding_metadata:
        result += "\n\n## Sources\n"
        for chunk in status.grounding_metadata.grounding_chunks:
            if hasattr(chunk, "web") and chunk.web:
                result += f"- [{chunk.web.title}]({chunk.web.uri})\n"

    print(result)

if __name__ == "__main__":
    main()
