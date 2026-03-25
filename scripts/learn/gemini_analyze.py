#!/usr/bin/env python3
"""
Analyze YouTube video using Gemini — outputs structured study notes (not timeline).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.core.local_env import get_local_env_value


def download_video(video_url: str, output_path: str) -> bool:
    cmd = [
        "yt-dlp",
        "-f", "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best",
        "--no-warnings", "--max-filesize", "200M",
        "-o", output_path, video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result.returncode == 0 and os.path.exists(output_path)


def analyze_with_gemini(video_path: str, title: str, language_hint: str = "ko") -> dict:
    try:
        from google import genai

        api_key = get_local_env_value(
            "WHIPPER_GEMINI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        )
        if not api_key:
            return {"success": False, "error": "GEMINI_API_KEY or GOOGLE_API_KEY not set"}

        client = genai.Client(api_key=api_key)

        print("Uploading video to Gemini...", file=sys.stderr)
        video_file = client.files.upload(file=video_path)

        print("Waiting for video processing...", file=sys.stderr)
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            return {"success": False, "error": "Video processing failed"}

        print("Analyzing with Gemini...", file=sys.stderr)

        lang = "The video is in English. Write ALL content in Korean, but keep direct quotes in English too." if language_hint == "en" else "Write in Korean."

        prompt = f"""Watch this entire YouTube video carefully. Title: "{title}"

{lang}

Your job: create STUDY NOTES that completely replace watching this video. Someone reading your notes should learn everything the video teaches, without ever watching it.

Output as valid JSON with this structure:

{{
  "summary": "2-3 sentence overview of what this video covers and why it matters.",
  "sections": [
    {{
      "title": "Section title based on TOPIC (not timestamp)",
      "content": [
        {{
          "type": "text",
          "text": "Markdown-formatted study note content. Use bullet points with indentation for hierarchy. Use **bold** for key terms and direct quotes. Write naturally — no [SPEAKER] or [ACTION] tags. Include everything: what was said, what was done, why it matters, how to do it. Be specific enough that the reader can actually DO what's taught."
        }},
        {{
          "type": "gif",
          "timestamp": 290,
          "duration": 8,
          "description": "What this GIF shows — be specific about what physical movement/technique is visible",
          "why_needed": "Why text alone can't convey this — what you need to SEE"
        }},
        {{
          "type": "text",
          "text": "More content after the GIF..."
        }},
        {{
          "type": "toggle",
          "title": "Toggle title (for supplementary detail)",
          "content": "Markdown content inside the toggle. Use for: repeated demonstrations, background theory, edge cases, Q&A from the video."
        }}
      ]
    }}
  ]
}}

CRITICAL RULES:

1. SECTION TITLES are based on TOPIC/CONCEPT, not timestamps. Good: "블로킹으로 먹이 주도권 잡기". Bad: "03:36 ~ 05:22".

2. TEXT CONTENT must be markdown with proper hierarchy:
   - Top-level bullets for main points
     - Indented bullets for details/explanations
     - Further indentation for sub-details
   - **Bold** for key terms, techniques, direct quotes from speaker
   - Write complete thoughts, not fragments
   - Include the WHY behind every instruction
   - For physical techniques: exact body positions, hand placements, angles

3. GIF entries: ONLY when the content genuinely CANNOT be understood from text alone.
   - Physical demonstrations where body position/movement matters
   - Visual techniques that need to be SEEN
   - NOT for: someone just talking, showing slides, pointing at things
   - Each GIF: specify exact timestamp (seconds) and duration (5-15 seconds)
   - Typically 3-6 GIFs per 10-minute video, placed EXACTLY where the action is described

4. TOGGLE entries: for content that supplements but isn't core:
   - Repeated demonstrations of the same technique
   - Background theory or analogies
   - Q&A exchanges from the video
   - Before/after comparisons

5. COMPLETENESS: every piece of information in the video must appear in the notes. If someone said it or showed it, it's in the notes. No summarizing away details.

6. Each section should have 3-15 content items. Sections should be 2-6 per video depending on length and topic changes.

7. Timestamp references: write timestamps in parentheses like (4:48). Do NOT include any youtube.com URLs in your output — the rendering system will convert timestamps to links automatically."""


        from google.genai import types
        config_kwargs = {
            "max_output_tokens": 65536,
            "response_mime_type": "application/json",
        }
        media_resolution = getattr(types, "MediaResolution", None)
        if media_resolution is not None and hasattr(
            media_resolution, "MEDIA_RESOLUTION_LOW"
        ):
            config_kwargs["media_resolution"] = (
                media_resolution.MEDIA_RESOLUTION_LOW
            )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except TypeError as exc:
            if "media_resolution" not in str(exc):
                raise
            config_kwargs.pop("media_resolution", None)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(**config_kwargs),
            )

        text = response.text.strip()
        result = json.loads(text)
        result["success"] = True

        try:
            client.files.delete(name=video_file.name)
        except Exception:
            pass

        return result

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON parse error: {e}", "raw_text": text[:3000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_url")
    parser.add_argument("--video-id", default="video")
    parser.add_argument("--title", default="")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--output", default="/tmp/gemini_results")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, f"{args.video_id}.mp4")
        print(f"Downloading: {args.title or args.video_url}", file=sys.stderr)
        if not download_video(args.video_url, video_path):
            found = False
            for ext in ["webm", "mkv"]:
                alt = os.path.join(tmpdir, f"{args.video_id}.{ext}")
                if os.path.exists(alt):
                    video_path = alt
                    found = True
                    break
            if not found:
                print(json.dumps({"success": False, "error": "Download failed"}))
                sys.exit(1)
        result = analyze_with_gemini(video_path, args.title, args.language)

    output_file = os.path.join(args.output, f"{args.video_id}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
