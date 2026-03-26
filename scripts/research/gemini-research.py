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


def extract_interaction_text(interaction) -> str:
    outputs = getattr(interaction, "outputs", None) or []
    texts = []
    for output in outputs:
        text = getattr(output, "text", None)
        if text:
            texts.append(text)
            continue
        parts = getattr(output, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                texts.append(part_text)
    return "\n\n".join(texts).strip()


def extract_grounding_sources(status) -> str:
    grounding = getattr(status, "grounding_metadata", None)
    grounding_chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
    if not grounding_chunks:
        return ""

    lines = ["## Sources"]
    for chunk in grounding_chunks:
        if hasattr(chunk, "web") and chunk.web:
            lines.append(f"- [{chunk.web.title}]({chunk.web.uri})")
    return "\n".join(lines)


def run_fast_fallback(client, prompt: str) -> str:
    from google.genai import types

    fallback_model = os.getenv("WHIPPER_GEMINI_RESEARCH_FALLBACK_MODEL", "gemini-2.5-pro").strip() or "gemini-2.5-pro"
    response = client.models.generate_content(
        model=fallback_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_budget=4096),
        ),
    )

    texts = []
    for part in response.candidates[0].content.parts:
        part_text = getattr(part, "text", None)
        if part_text:
            texts.append(part_text)

    result = "\n".join(texts).strip()
    sources = extract_grounding_sources(response.candidates[0])
    note = (
        "## Fallback Note\n"
        "Gemini deep research background job did not complete within the operational wait budget, "
        "so a search-grounded synchronous fallback was used.\n\n"
    )
    if sources:
        result = f"{result}\n\n{sources}".strip()
    return note + result if result else note.rstrip()

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
        input=prompt,
        agent=model_name,
        background=True,
        store=True,
    )

    # Poll until complete (max 30 min)
    max_wait = 1800
    fallback_wait = int(os.getenv("WHIPPER_RESEARCH_DEEP_WAIT_SECONDS", "180"))
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        status = client.interactions.get(interaction.id)
        if status.status == "completed":
            break
        if status.status in {"failed", "cancelled", "incomplete"}:
            print(f"Error: Research failed — {status.error}", file=sys.stderr)
            sys.exit(1)
        if elapsed >= fallback_wait:
            print("⚠️ Deep research slow; using fast Gemini fallback", file=sys.stderr)
            print(run_fast_fallback(client, prompt))
            return
        time.sleep(poll_interval)
        elapsed += poll_interval
        print(f"⏳ Research in progress... ({elapsed}s)", file=sys.stderr)

    if elapsed >= max_wait:
        print("Error: Research timed out after 30 minutes", file=sys.stderr)
        sys.exit(1)

    # Extract result
    result = extract_interaction_text(status)
    if not result:
        result = json.dumps(status.to_json_dict(), ensure_ascii=False, indent=2)

    # Extract sources
    sources = extract_grounding_sources(status)
    if sources:
        result += f"\n\n{sources}\n"

    print(result)

if __name__ == "__main__":
    main()
