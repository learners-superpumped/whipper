#!/usr/bin/env python3
"""OpenAI thinking with web search. Reads prompt from stdin or arg, prints response to stdout."""
import sys
import os
import json
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
    model_name = models.get("think", {}).get("openai", "o3")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model_name,
        input=prompt,
        tools=[{"type": "web_search_preview"}],
    )

    # Extract text and annotations
    result_parts = []
    sources = []
    for item in response.output:
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
