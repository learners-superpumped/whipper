#!/usr/bin/env python3
"""
Render v3 study note JSON (sections with mixed content) to Notion markdown.
"""

import argparse
import json
import os
import re
import sys


def _convert_timestamps(text: str, video_url: str) -> str:
    """Convert bare (MM:SS) timestamps to YouTube links in text."""
    # Remove any YouTube URLs Gemini might have generated, keeping link text
    text = re.sub(
        r'\[([^\]]*)\]\(https?://(?:www\.)?youtube\.com/watch\?[^)]+\)',
        lambda m: m.group(1),
        text
    )
    # Convert bare (H:MM:SS) or (MM:SS) timestamps to YouTube links
    def _ts_to_link(m):
        ts = m.group(1)
        parts = ts.split(":")
        if len(parts) == 3:
            secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            secs = int(parts[0]) * 60 + int(parts[1])
        return f'[{ts}]({video_url}&t={secs}s)'
    text = re.sub(r'\((\d{1,2}:\d{2}(?::\d{2})?)\)', _ts_to_link, text)
    return text


def render_study_note_to_notion_md(data: dict) -> str:
    meta = data.get("meta", {})
    sections = data.get("sections", [])
    transcript = data.get("transcript", {})
    summary = data.get("summary", "")
    video_url = meta.get("video_url", "")

    lines = []

    # Embed YouTube video at the top of the page
    if video_url:
        lines.append(f"[{meta.get('title', 'YouTube 영상')}]({video_url})")
        lines.append("")

    # Metadata
    vc = meta.get("view_count", 0)
    dur = meta.get("duration", 0)
    dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
    parts = [f"조회수: {vc:,}" if vc else "", f"길이: {dur_str}" if dur_str else ""]
    info = " | ".join(p for p in parts if p)
    if info:
        lines.append(f"> {info}")
        lines.append("")

    # Summary
    if summary:
        lines.append(summary)
        lines.append("")

    lines.append("---")
    lines.append("")

    # Sections
    for section in sections:
        title = section.get("title", "")
        lines.append(f"## {title}")
        lines.append("")

        for item in section.get("content", []):
            item_type = item.get("type", "text")

            if item_type == "text":
                text = _convert_timestamps(item.get("text", ""), video_url)
                lines.append(text)
                lines.append("")

            elif item_type == "gif":
                url = item.get("public_url", "")
                desc = item.get("description", "")
                if url:
                    lines.append(f"![{desc}]({url})")
                    lines.append("")

            elif item_type == "toggle":
                toggle_title = item.get("title", "더 보기")
                toggle_content = _convert_timestamps(item.get("content", ""), video_url)
                lines.append("<details>")
                lines.append(f"<summary>{toggle_title}</summary>")
                lines.append("")
                lines.append(toggle_content)
                lines.append("")
                lines.append("</details>")
                lines.append("")

    # Full transcript toggle
    full_text = transcript.get("full_text", "")
    if full_text:
        lines.append("---")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>전체 스크립트 (원문)</summary>")
        lines.append("")
        chunk_size = 8000
        for i in range(0, len(full_text), chunk_size):
            lines.append(full_text[i:i + chunk_size])
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--output")
    args = parser.parse_args()

    with open(args.input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    md = render_study_note_to_notion_md(data)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
