#!/usr/bin/env python3
"""Gemini thinking with web search. Reads prompt from stdin or arg, prints response to stdout."""
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

    api_key = get_local_env_value("WHIPPER_GEMINI_API_KEY", "GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Load model from config
    config_path = os.path.join(os.path.dirname(__file__), "../../config/models.json")
    with open(config_path) as f:
        models = json.load(f)
    model_name = models.get("think", {}).get("gemini", "gemini-2.5-pro")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_budget=8192),
        ),
    )

    # Extract text and sources
    output_parts = []
    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            output_parts.append(part.text)

    result = "\n".join(output_parts)

    # Extract grounding sources if available
    grounding = getattr(response.candidates[0], "grounding_metadata", None)
    if grounding and hasattr(grounding, "grounding_chunks"):
        result += "\n\n## Sources\n"
        for chunk in grounding.grounding_chunks:
            if hasattr(chunk, "web") and chunk.web:
                result += f"- [{chunk.web.title}]({chunk.web.uri})\n"

    print(result)

if __name__ == "__main__":
    main()
