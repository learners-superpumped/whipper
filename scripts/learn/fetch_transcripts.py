#!/usr/bin/env python3
"""
Fetch transcripts for YouTube videos using youtube-transcript-api.
Usage: python fetch_transcripts.py <video_ids_json_file> [--output <output_dir>]
Reads a JSON file with video IDs, fetches transcripts, writes individual JSON files.
"""

import argparse
import json
import os
import sys

from youtube_transcript_api import YouTubeTranscriptApi


def fetch_transcript(video_id: str) -> dict:
    """Fetch transcript for a single video. Returns dict with text and language info."""
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)

        # Priority: Korean manual > Korean auto > English manual > English auto > any
        transcript = None
        language = None
        is_auto_generated = False

        # Try Korean first
        try:
            transcript = transcript_list.find_transcript(["ko"])
            language = "ko"
            is_auto_generated = transcript.is_generated
        except Exception:
            pass

        # Try English
        if transcript is None:
            try:
                transcript = transcript_list.find_transcript(["en"])
                language = "en"
                is_auto_generated = transcript.is_generated
            except Exception:
                pass

        # Try any available
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

        # Build full text and timestamped segments
        segments = []
        full_text = []
        for entry in fetched:
            seg = {
                "start": round(entry.start, 1),
                "duration": round(entry.duration, 1),
                "text": entry.text,
            }
            segments.append(seg)
            full_text.append(entry.text)

        return {
            "success": True,
            "language": language,
            "is_auto_generated": is_auto_generated,
            "full_text": " ".join(full_text),
            "segments": segments,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcripts")
    parser.add_argument("input_file", help="JSON file with video data (needs 'id' field)")
    parser.add_argument("--output", default="./transcripts", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    with open(args.input_file, "r") as f:
        videos = json.load(f)

    results = []
    for i, video in enumerate(videos):
        video_id = video["id"]
        title = video.get("title", video_id)
        print(f"[{i+1}/{len(videos)}] Fetching transcript: {title}", file=sys.stderr)

        transcript_data = fetch_transcript(video_id)
        transcript_data["video_id"] = video_id
        transcript_data["title"] = title
        transcript_data["url"] = video.get("url", f"https://www.youtube.com/watch?v={video_id}")
        transcript_data["view_count"] = video.get("view_count", 0)

        # Save individual transcript
        output_file = os.path.join(args.output, f"{video_id}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)

        results.append({
            "video_id": video_id,
            "title": title,
            "success": transcript_data["success"],
            "language": transcript_data.get("language"),
            "file": output_file,
            "error": transcript_data.get("error"),
        })

    # Summary output
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
