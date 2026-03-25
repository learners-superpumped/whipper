#!/usr/bin/env python3
"""
Assemble study note JSON from Gemini structured analysis + transcript + media.
New v3 format: sections with mixed content (text, gif, toggle).
"""

import argparse
import json
import os
import sys
from datetime import datetime


def load_json(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_study_note(gemini: dict, transcript: dict, media_urls: dict,
                     video_id: str, video_url: str, title: str,
                     view_count: int = 0, duration: int = 0,
                     upload_date: str = "") -> dict:

    language = transcript.get("language", "ko")
    analysis_mode = "gemini" if gemini.get("success", False) else "transcript"

    # Parse uploaded media for this video
    video_media = media_urls.get(video_id, [])
    uploaded_gifs = {int(m["timestamp"]): m["url"] for m in video_media if m.get("type") == "gif" and m.get("url")}

    # Process sections — attach uploaded GIF URLs to gif content items
    sections = gemini.get("sections", []) if gemini.get("success") else []
    for section in sections:
        for item in section.get("content", []):
            if item.get("type") == "gif":
                ts = item.get("timestamp", 0)
                # Find closest uploaded GIF (within 10s)
                best_url = None
                best_diff = 11
                for gif_ts, gif_url in uploaded_gifs.items():
                    diff = abs(gif_ts - ts)
                    if diff < best_diff:
                        best_diff = diff
                        best_url = gif_url
                item["public_url"] = best_url or ""

    transcript_section = {
        "language": transcript.get("language", language),
        "is_auto_generated": transcript.get("is_auto_generated", True),
        "full_text": transcript.get("full_text", ""),
    }

    return {
        "meta": {
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "view_count": view_count,
            "duration": duration,
            "upload_date": upload_date,
            "language": language,
            "analysis_mode": analysis_mode,
            "generated_at": datetime.now().isoformat(),
        },
        "summary": gemini.get("summary", ""),
        "sections": sections,
        "transcript": transcript_section,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gemini-result", default="")
    parser.add_argument("--transcript", default="")
    parser.add_argument("--media-urls", default="")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--video-url", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--view-count", type=int, default=0)
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--upload-date", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    gemini = load_json(args.gemini_result)
    transcript = load_json(args.transcript)
    media_urls = load_json(args.media_urls)

    result = build_study_note(
        gemini=gemini, transcript=transcript, media_urls=media_urls,
        video_id=args.video_id,
        video_url=args.video_url or f"https://www.youtube.com/watch?v={args.video_id}",
        title=args.title, view_count=args.view_count,
        duration=args.duration, upload_date=args.upload_date,
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Study note saved to {args.output}", file=sys.stderr)
    print(json.dumps({"success": True, "output": args.output}))


if __name__ == "__main__":
    main()
