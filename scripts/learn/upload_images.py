#!/usr/bin/env python3
"""
Upload screenshots and GIFs to catbox.moe, return public URLs grouped by video_id.
Usage: python upload_images.py /tmp/yt_screenshots [/tmp/yt_gifs]
Output: JSON { "video_id": [{"url": "...", "timestamp": "120", "type": "screenshot|gif", "file": "..."}] }
"""

import glob
import json
import os
import subprocess
import sys
import time


def upload_file(filepath: str, retries: int = 3) -> str:
    """Upload a file to catbox.moe with retries."""
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["curl", "-s", "-F", "reqtype=fileupload",
                 "-F", f"fileToUpload=@{filepath}",
                 "https://catbox.moe/user/api.php"],
                capture_output=True, text=True, timeout=60
            )
            url = r.stdout.strip()
            if url.startswith("http"):
                return url
        except Exception as e:
            print(f"  Upload attempt {attempt+1} error: {e}", file=sys.stderr)
        if attempt < retries - 1:
            time.sleep(2)
    return ""


def parse_screenshot_filename(basename: str) -> tuple:
    """Parse {video_id}_{index}_{seconds}s.jpg -> (video_id, seconds, 'screenshot')"""
    name = basename.rsplit(".", 1)[0]  # remove extension
    parts = name.rsplit("_", 2)
    if len(parts) >= 3:
        video_id = parts[0]
        timestamp_sec = parts[2].replace("s", "")
        return video_id, timestamp_sec, "screenshot"
    return None, None, None


def parse_gif_filename(basename: str) -> tuple:
    """Parse gif filenames in multiple formats:
    {video_id}_gif_{seconds}s.gif
    {video_id}_action_{start}s_{dur}s.gif
    """
    name = basename.rsplit(".", 1)[0]
    # Try action format: {video_id}_action_{start}s_{dur}s
    parts = name.split("_action_")
    if len(parts) == 2:
        video_id = parts[0]
        rest = parts[1]  # e.g. "216s_15s"
        timestamp_sec = rest.split("_")[0].replace("s", "")
        return video_id, timestamp_sec, "gif"
    # Try old format: {video_id}_gif_{seconds}s
    parts = name.rsplit("_", 2)
    if len(parts) >= 3 and parts[1] == "gif":
        video_id = parts[0]
        timestamp_sec = parts[2].replace("s", "")
        return video_id, timestamp_sec, "gif"
    return None, None, None


def main():
    dirs = sys.argv[1:] if len(sys.argv) > 1 else ["/tmp/yt_screenshots"]

    # Collect all files
    files = []
    for d in dirs:
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
            files.extend(glob.glob(os.path.join(d, ext)))
    files.sort()

    if not files:
        print(json.dumps({}))
        return

    results = {}
    total = len(files)

    for i, f in enumerate(files):
        basename = os.path.basename(f)
        ext = basename.rsplit(".", 1)[-1].lower()

        if ext == "gif":
            video_id, timestamp_sec, media_type = parse_gif_filename(basename)
        else:
            video_id, timestamp_sec, media_type = parse_screenshot_filename(basename)

        if not video_id:
            print(f"  Skipping unparseable filename: {basename}", file=sys.stderr)
            continue

        sec = int(timestamp_sec)
        ts_formatted = f"{sec // 60:02d}:{sec % 60:02d}"

        print(f"[{i+1}/{total}] Uploading {basename}...", file=sys.stderr)
        url = upload_file(f)

        if url:
            if video_id not in results:
                results[video_id] = []
            results[video_id].append({
                "url": url,
                "timestamp": timestamp_sec,
                "timestamp_formatted": ts_formatted,
                "type": media_type,
                "file": basename,
            })
            print(f"  -> {url}", file=sys.stderr)
        else:
            print(f"  FAILED", file=sys.stderr)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
