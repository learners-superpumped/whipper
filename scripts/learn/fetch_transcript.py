#!/usr/bin/env python3
"""
Fetch transcript for a single YouTube video.
Usage: python fetch_transcript.py <video_url_or_id> --output /tmp/transcript.json
"""

import argparse
import json
import re
import sys

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str:
    """Extract video ID from URL or return as-is if already an ID."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return url_or_id


def fetch_transcript(video_id: str) -> dict:
    """Fetch transcript for a single video."""
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)

        transcript = None
        language = None
        is_auto_generated = False

        # Priority: Korean manual > Korean auto > English manual > English auto > any
        for lang_codes in [["ko"], ["en"]]:
            try:
                transcript = transcript_list.find_transcript(lang_codes)
                language = lang_codes[0]
                is_auto_generated = transcript.is_generated
                break
            except Exception:
                continue

        if transcript is None:
            try:
                for t in transcript_list:
                    transcript = t
                    language = t.language_code
                    is_auto_generated = t.is_generated
                    break
            except Exception:
                pass

        if transcript is None:
            return {"success": False, "error": "No transcript available"}

        fetched = transcript.fetch()
        segments = []
        full_text_parts = []
        for entry in fetched:
            segments.append({
                "start": round(entry.start, 1),
                "duration": round(entry.duration, 1),
                "text": entry.text,
            })
            full_text_parts.append(entry.text)

        return {
            "success": True,
            "video_id": video_id,
            "language": language,
            "is_auto_generated": is_auto_generated,
            "full_text": " ".join(full_text_parts),
            "segments": segments,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcript for a single video")
    parser.add_argument("video", help="YouTube video URL or ID")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    video_id = extract_video_id(args.video)
    print(f"Fetching transcript for {video_id}...", file=sys.stderr)

    result = fetch_transcript(video_id)

    if args.output:
        import os
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
