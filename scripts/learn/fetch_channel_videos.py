#!/usr/bin/env python3
"""
Fetch video list from a YouTube channel using yt-dlp.
Usage: python fetch_channel_videos.py <channel_url> [--sort views|date] [--limit 50]
Output: JSON array of video metadata to stdout
"""

import argparse
import json
import subprocess
import sys


def fetch_videos(channel_url: str, sort_by: str = "date", limit: int = 50) -> list[dict]:
    """Fetch video list from a YouTube channel."""

    # Use /videos tab for the channel
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"

    # yt-dlp command to extract flat playlist (metadata only, no download)
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--extractor-args", "youtubetab:approximate_date",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        print(f"Error fetching channel: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            video = {
                "id": data.get("id", ""),
                "title": data.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                "view_count": data.get("view_count", 0) or 0,
                "duration": data.get("duration", 0) or 0,
                "upload_date": data.get("upload_date", ""),
                "description": (data.get("description", "") or "")[:200],
            }
            videos.append(video)
        except json.JSONDecodeError:
            continue

    # Sort
    if sort_by == "views":
        videos.sort(key=lambda v: v["view_count"], reverse=True)
    else:  # date (newest first, default from yt-dlp)
        pass

    return videos[:limit]


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube channel videos")
    parser.add_argument("channel_url", help="YouTube channel URL")
    parser.add_argument("--sort", choices=["views", "date"], default="date",
                        help="Sort by views or date (default: date)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Number of videos to fetch (default: 50)")
    args = parser.parse_args()

    videos = fetch_videos(args.channel_url, args.sort, args.limit)
    print(json.dumps(videos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
