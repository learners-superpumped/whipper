#!/usr/bin/env python3
"""
Assemble a study note JSON from Gemini analysis, transcript, and media URLs.
Usage:
  python generate_study_note.py \
    --gemini-result /tmp/gemini_results/<video_id>.json \
    --transcript /tmp/yt_transcripts/<video_id>.json \
    --media-urls /tmp/media_urls.json \
    --video-id <video_id> \
    --video-url <url> \
    --title "<title>" \
    --output /tmp/yt_study_notes/<video_id>.json
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


def deduplicate_media(screenshots: list, gifs: list) -> tuple:
    """Remove screenshots that have GIFs at the same timestamp."""
    gif_timestamps = {int(g.get("timestamp", 0)) for g in gifs}
    filtered_screenshots = [
        s for s in screenshots
        if int(s.get("timestamp", -1)) not in gif_timestamps
    ]
    return filtered_screenshots, gifs


def build_study_note(gemini: dict, transcript: dict, media_urls: dict,
                     video_id: str, video_url: str, title: str,
                     view_count: int = 0, duration: int = 0,
                     upload_date: str = "") -> dict:
    """Build the study note JSON contract."""

    # Determine language from transcript or gemini
    language = transcript.get("language", "ko")
    analysis_mode = "gemini" if gemini.get("success", False) else "transcript"

    # Parse media URLs for this video
    video_media = media_urls.get(video_id, [])
    raw_screenshots = [m for m in video_media if m.get("type") == "screenshot"]
    raw_gifs = [m for m in video_media if m.get("type") == "gif"]

    # Deduplicate
    screenshots, gifs = deduplicate_media(raw_screenshots, raw_gifs)

    # Format screenshots for output
    media_screenshots = [
        {
            "timestamp": int(s["timestamp"]),
            "timestamp_formatted": s["timestamp_formatted"],
            "public_url": s["url"],
        }
        for s in screenshots if s.get("url")
    ]
    media_gifs = [
        {
            "timestamp": int(g["timestamp"]),
            "timestamp_formatted": g["timestamp_formatted"],
            "public_url": g["url"],
        }
        for g in gifs if g.get("url")
    ]

    # Build study_note section from gemini result
    if gemini.get("success"):
        study_note = {
            "one_line_summary": gemini.get("one_line_summary", ""),
            "detailed_summary": gemini.get("detailed_summary", ""),
            "target_audience": gemini.get("target_audience", ""),
            "difficulty_level": gemini.get("difficulty_level", ""),
            "prerequisites": gemini.get("prerequisites", ""),
            "topics": gemini.get("topics", []),
            "concepts": gemini.get("concepts", []),
            "full_lecture_notes": gemini.get("full_lecture_notes", []),
            "step_by_step": gemini.get("step_by_step", []),
            "demonstrations": gemini.get("demonstrations", []),
            "common_mistakes": gemini.get("common_mistakes", []),
            "qa_from_video": gemini.get("qa_from_video", []),
            "quotes": gemini.get("quotes", []),
            "visual_key_moments": gemini.get("visual_key_moments", []),
            "keywords": gemini.get("keywords", []),
        }
    else:
        # Minimal structure for transcript-only mode
        study_note = {
            "one_line_summary": "",
            "detailed_summary": "",
            "target_audience": "",
            "difficulty_level": "",
            "prerequisites": "",
            "topics": [],
            "concepts": [],
            "full_lecture_notes": [],
            "step_by_step": [],
            "demonstrations": [],
            "common_mistakes": [],
            "qa_from_video": [],
            "quotes": [],
            "visual_key_moments": [],
            "keywords": [],
        }

    # Build transcript section
    transcript_section = {
        "language": transcript.get("language", language),
        "is_auto_generated": transcript.get("is_auto_generated", True),
        "full_text": transcript.get("full_text", ""),
        "segments": transcript.get("segments", []),
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
        "study_note": study_note,
        "media": {
            "screenshots": media_screenshots,
            "gifs": media_gifs,
        },
        "transcript": transcript_section,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate study note JSON")
    parser.add_argument("--gemini-result", default="", help="Gemini analysis JSON path")
    parser.add_argument("--transcript", default="", help="Transcript JSON path")
    parser.add_argument("--media-urls", default="", help="Media URLs JSON path")
    parser.add_argument("--video-id", required=True, help="Video ID")
    parser.add_argument("--video-url", default="", help="Video URL")
    parser.add_argument("--title", default="", help="Video title")
    parser.add_argument("--view-count", type=int, default=0, help="View count")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds")
    parser.add_argument("--upload-date", default="", help="Upload date")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    gemini = load_json(args.gemini_result)
    transcript = load_json(args.transcript)
    media_urls = load_json(args.media_urls)

    result = build_study_note(
        gemini=gemini,
        transcript=transcript,
        media_urls=media_urls,
        video_id=args.video_id,
        video_url=args.video_url or f"https://www.youtube.com/watch?v={args.video_id}",
        title=args.title,
        view_count=args.view_count,
        duration=args.duration,
        upload_date=args.upload_date,
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Study note saved to {args.output}", file=sys.stderr)
    print(json.dumps({"success": True, "output": args.output}))


if __name__ == "__main__":
    main()
