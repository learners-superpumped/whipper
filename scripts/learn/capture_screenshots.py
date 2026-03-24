#!/usr/bin/env python3
"""
Capture screenshots from YouTube videos at key timestamps.
Usage: python capture_screenshots.py <video_url> --timestamps 0 60 120 --output /tmp/screenshots/
Uses yt-dlp to download and ffmpeg to extract frames.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile


def capture_screenshots(
    video_url: str,
    timestamps: list[float],
    output_dir: str,
    video_id: str = "",
    max_screenshots: int = 10,
) -> list[dict]:
    """Capture screenshots at specified timestamps."""
    os.makedirs(output_dir, exist_ok=True)

    # Limit timestamps
    timestamps = sorted(timestamps)[:max_screenshots]

    # Download video at lowest quality sufficient for screenshots
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")

        print(f"Downloading video: {video_url}", file=sys.stderr)
        dl_cmd = [
            "yt-dlp",
            "-f", "worst[ext=mp4]/worst",
            "--no-warnings",
            "-o", video_path,
            video_url,
        ]
        result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"Download failed: {result.stderr}", file=sys.stderr)
            return []

        if not os.path.exists(video_path):
            # Try alternate extension
            for ext in ["webm", "mkv"]:
                alt = os.path.join(tmpdir, f"video.{ext}")
                if os.path.exists(alt):
                    video_path = alt
                    break

        if not os.path.exists(video_path):
            print("Video file not found after download", file=sys.stderr)
            return []

        # Extract frames at each timestamp
        screenshots = []
        for i, ts in enumerate(timestamps):
            minutes = int(ts) // 60
            seconds = int(ts) % 60
            timestamp_str = f"{minutes:02d}:{seconds:02d}"
            filename = f"{video_id}_{i:03d}_{int(ts)}s.jpg"
            output_path = os.path.join(output_dir, filename)

            ff_cmd = [
                "ffmpeg",
                "-ss", str(ts),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                "-y",
                output_path,
            ]
            ff_result = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=30)

            if ff_result.returncode == 0 and os.path.exists(output_path):
                screenshots.append({
                    "timestamp": ts,
                    "timestamp_str": timestamp_str,
                    "file": output_path,
                    "filename": filename,
                })
                print(f"  Captured: {timestamp_str}", file=sys.stderr)
            else:
                print(f"  Failed: {timestamp_str}", file=sys.stderr)

    return screenshots


def select_key_timestamps(transcript_segments: list[dict], num_screenshots: int = 8) -> list[float]:
    """Select key timestamps from transcript segments.
    Strategy: evenly space across the video, avoiding the very start/end.
    """
    if not transcript_segments:
        return []

    total_duration = transcript_segments[-1]["start"] + transcript_segments[-1].get("duration", 5)

    # Skip first 10s and last 10s
    start = min(10.0, total_duration * 0.05)
    end = max(total_duration - 10.0, total_duration * 0.95)

    if end <= start:
        return [total_duration / 2]

    interval = (end - start) / (num_screenshots + 1)
    timestamps = [start + interval * (i + 1) for i in range(num_screenshots)]

    return timestamps


def main():
    parser = argparse.ArgumentParser(description="Capture YouTube video screenshots")
    parser.add_argument("video_url", help="YouTube video URL")
    parser.add_argument("--timestamps", nargs="+", type=float, default=None,
                        help="Specific timestamps in seconds")
    parser.add_argument("--transcript", default=None,
                        help="Transcript JSON file (to auto-select timestamps)")
    parser.add_argument("--num", type=int, default=8,
                        help="Number of screenshots (default: 8)")
    parser.add_argument("--output", default="/tmp/yt_screenshots",
                        help="Output directory")
    parser.add_argument("--video-id", default="video",
                        help="Video ID for filenames")
    args = parser.parse_args()

    timestamps = args.timestamps

    if timestamps is None and args.transcript:
        with open(args.transcript) as f:
            data = json.load(f)
        segments = data.get("segments", [])
        timestamps = select_key_timestamps(segments, args.num)
    elif timestamps is None:
        # Default: capture at 25%, 50%, 75% of typical video
        timestamps = [30, 60, 120, 180, 240, 300, 360, 420]

    screenshots = capture_screenshots(
        args.video_url, timestamps, args.output,
        video_id=args.video_id, max_screenshots=args.num,
    )

    print(json.dumps(screenshots, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
