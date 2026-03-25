#!/usr/bin/env python3
"""
Extract GIFs for all has_action timeline entries from a Gemini result.
Each GIF covers the exact timestamp range of the action segment.

Usage:
  python extract_action_gifs.py <video_url> \
    --gemini-result /tmp/gemini/vid.json \
    --video-id <id> \
    --output /tmp/gifs
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def ts_to_sec(ts: str) -> int:
    if not ts or ":" not in ts:
        return 0
    parts = ts.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 0


def download_video(video_url: str, output_path: str) -> bool:
    cmd = [
        "yt-dlp",
        "-f", "best[height<=480][ext=mp4]/best[height<=480]/worst[ext=mp4]/worst",
        "--no-warnings",
        "-o", output_path,
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0 and os.path.exists(output_path):
        return True
    base = output_path.rsplit(".", 1)[0]
    for ext in ["webm", "mkv", "mp4"]:
        alt = f"{base}.{ext}"
        if os.path.exists(alt):
            if alt != output_path:
                os.rename(alt, output_path)
            return True
    return False


def extract_gif(video_path: str, start: float, duration: float,
                output_path: str, width: int = 480, fps: int = 10) -> bool:
    # Cap duration at 15 seconds for file size
    duration = min(duration, 15)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", video_path,
        "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
        "-loop", "0",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode == 0 and os.path.exists(output_path)


def main():
    parser = argparse.ArgumentParser(description="Extract action GIFs from timeline")
    parser.add_argument("video_url", help="YouTube video URL")
    parser.add_argument("--gemini-result", required=True, help="Gemini JSON with timeline")
    parser.add_argument("--video-id", default="video", help="Video ID")
    parser.add_argument("--output", default="/tmp/yt_gifs", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    with open(args.gemini_result) as f:
        data = json.load(f)

    # Support both v2 (timeline) and v3 (sections) format
    gif_entries = []
    if "sections" in data:
        for section in data.get("sections", []):
            for item in section.get("content", []):
                if item.get("type") == "gif":
                    gif_entries.append(item)
    else:
        gif_entries = [e for e in data.get("timeline", []) if e.get("has_action")]

    if not gif_entries:
        print(json.dumps({"success": True, "video_id": args.video_id, "gifs": []}))
        return

    print(f"Found {len(gif_entries)} GIF segments to extract", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, f"{args.video_id}.mp4")
        print("Downloading video...", file=sys.stderr)

        if not download_video(args.video_url, video_path):
            print(json.dumps({"success": False, "error": "Download failed"}))
            sys.exit(1)

        gifs = []
        for i, entry in enumerate(gif_entries):
            start_sec = entry.get("timestamp", 0)
            if isinstance(start_sec, str):
                start_sec = ts_to_sec(start_sec)
            duration = entry.get("duration", 8)

            filename = f"{args.video_id}_action_{start_sec}s_{duration}s.gif"
            output_file = os.path.join(args.output, filename)

            ts = entry.get("timestamp", 0)
            if isinstance(ts, int):
                ts_fmt = f"{ts // 60}:{ts % 60:02d}"
            else:
                ts_fmt = str(ts)
            print(f"[{i+1}/{len(gif_entries)}] {ts_fmt} ({duration}s)...", file=sys.stderr)

            if extract_gif(video_path, start_sec, duration, output_file):
                size_kb = os.path.getsize(output_file) / 1024
                gifs.append({
                    "timestamp": start_sec,
                    "timestamp_formatted": ts_fmt,
                    "duration": min(duration, 15),
                    "file": output_file,
                    "filename": filename,
                    "size_kb": round(size_kb, 1),
                })
                print(f"  -> {filename} ({size_kb:.0f}KB)", file=sys.stderr)
            else:
                print(f"  FAILED", file=sys.stderr)

    result = {
        "success": len(gifs) > 0,
        "video_id": args.video_id,
        "gifs": gifs,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
