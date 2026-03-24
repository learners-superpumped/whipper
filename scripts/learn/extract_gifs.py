#!/usr/bin/env python3
"""
Extract short GIF clips from YouTube videos at specified timestamps.
Uses yt-dlp to download + ffmpeg to extract GIF around each timestamp.

Usage:
  python extract_gifs.py <video_url> \
    --timestamps 279 414 549 \
    --duration 4 \
    --video-id <id> \
    --output /tmp/yt_gifs

Each GIF is ~3-5 seconds centered on the timestamp, 480px wide, 10fps.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def download_video(video_url: str, output_path: str) -> bool:
    """Download video at low quality for GIF extraction."""
    cmd = [
        "yt-dlp",
        "-f", "worst[ext=mp4]/worst",
        "--no-warnings",
        "-o", output_path,
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0 and os.path.exists(output_path):
        return True
    # Check for alternate extensions
    base = output_path.rsplit(".", 1)[0]
    for ext in ["webm", "mkv", "mp4"]:
        alt = f"{base}.{ext}"
        if os.path.exists(alt):
            if alt != output_path:
                os.rename(alt, output_path)
            return True
    return False


def extract_gif(
    video_path: str,
    timestamp: float,
    duration: float,
    output_path: str,
    width: int = 480,
    fps: int = 10,
) -> bool:
    """Extract a GIF from video at given timestamp."""
    # Start half-duration before the timestamp
    start = max(0, timestamp - duration / 2)

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


def format_timestamp(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def main():
    parser = argparse.ArgumentParser(description="Extract GIFs from YouTube video")
    parser.add_argument("video_url", help="YouTube video URL")
    parser.add_argument("--timestamps", nargs="+", type=float, required=True,
                        help="Timestamps in seconds to extract GIFs from")
    parser.add_argument("--duration", type=float, default=4,
                        help="GIF duration in seconds (default: 4)")
    parser.add_argument("--width", type=int, default=480,
                        help="GIF width in pixels (default: 480)")
    parser.add_argument("--video-id", default="video", help="Video ID for filenames")
    parser.add_argument("--output", default="/tmp/yt_gifs", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, f"{args.video_id}.mp4")

        print(f"Downloading video...", file=sys.stderr)
        if not download_video(args.video_url, video_path):
            print(json.dumps({"success": False, "error": "Download failed"}))
            sys.exit(1)

        gifs = []
        for i, ts in enumerate(args.timestamps):
            filename = f"{args.video_id}_gif_{int(ts)}s.gif"
            output_file = os.path.join(args.output, filename)

            print(f"[{i+1}/{len(args.timestamps)}] Extracting GIF at {format_timestamp(ts)}...", file=sys.stderr)
            if extract_gif(video_path, ts, args.duration, output_file, args.width):
                size_kb = os.path.getsize(output_file) / 1024
                gifs.append({
                    "timestamp": ts,
                    "timestamp_formatted": format_timestamp(ts),
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
