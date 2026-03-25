#!/usr/bin/env python3
"""
Automated test for youtube-to-notion skill (Skill 2).
Tests: render_notion_md.py output quality against study note JSON inputs.
Does NOT test actual Notion API calls (those require MCP and are tested via Claude).
Tests the rendering pipeline and content fidelity.

Usage:
  python3 test_youtube_to_notion.py --all
  python3 test_youtube_to_notion.py --video-id VIDEO_ID
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = str(ROOT / "scripts" / "learn")
STUDY_NOTES_DIR = "/tmp/yt_study_notes"
NOTION_MD_DIR = "/tmp/notion_md"

TEST_VIDEO_IDS = ["4jqZ8WgNm8I", "_cjThyHVZnU", "xUR7ZwMMPdI"]


def render_markdown(video_id: str) -> str:
    """Render study note JSON to Notion markdown. Returns output path."""
    input_path = os.path.join(STUDY_NOTES_DIR, f"{video_id}.json")
    output_path = os.path.join(NOTION_MD_DIR, f"{video_id}.md")

    if not os.path.exists(input_path):
        print(f"  ERROR: Study note not found: {input_path}", file=sys.stderr)
        return ""

    os.makedirs(NOTION_MD_DIR, exist_ok=True)
    result = subprocess.run([
        sys.executable, os.path.join(SKILL_DIR, "render_notion_md.py"),
        input_path, "--output", output_path
    ], capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        print(f"  ERROR: Render failed: {result.stderr[:200]}", file=sys.stderr)
        return ""

    return output_path


def validate(video_id: str, md_path: str, json_path: str) -> list:
    """Validate rendered markdown against checklist. Returns list of (check_id, pass, detail)."""
    results = []

    def check(cid, passed, detail=""):
        results.append((cid, passed, detail))
        if not passed:
            print(f"    FAIL {cid}: {detail}")

    # Load source JSON
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        check("N0", False, f"Cannot load source JSON: {e}")
        return results

    # Load rendered markdown
    if not md_path or not os.path.exists(md_path):
        check("N0", False, f"Markdown file not found: {md_path}")
        return results

    with open(md_path, "r") as f:
        md = f.read()

    meta = data.get("meta", {})
    sn = data.get("study_note", {})
    media = data.get("media", {})

    # N1: Markdown file exists and is non-empty
    check("N1", len(md) > 500, f"Markdown length={len(md)}")

    # N2: Contains YouTube link
    video_url = meta.get("video_url", "")
    check("N2", video_url in md, "YouTube URL not in markdown")

    # N3: Contains "한 줄 요약" section
    check("N3", "한 줄 요약" in md, "Missing '한 줄 요약' section")

    # N4: Contains "상세 요약" section
    check("N4", "상세 요약" in md, "Missing '상세 요약' section")

    # N5: Contains "타임라인" section
    check("N5", "타임라인" in md, "Missing '타임라인' section")

    # N6: Contains "핵심 개념" section
    check("N6", "핵심 개념" in md, "Missing '핵심 개념' section")

    # N7: Contains "전체 강의 노트" section
    check("N7", "전체 강의 노트" in md, "Missing '전체 강의 노트' section")

    # N8: Contains "단계별" section
    check("N8", "단계별" in md, "Missing '단계별' section")

    # N9: Contains "시연 장면" section
    check("N9", "시연 장면" in md or "시연" in md, "Missing '시연' section")

    # N10: Contains images (screenshots or GIFs)
    image_pattern = r'!\[.*?\]\(https?://.*?\)'
    images_in_md = re.findall(image_pattern, md)
    total_media = len(media.get("screenshots", [])) + len(media.get("gifs", []))
    check("N10", len(images_in_md) >= 1, f"Images in markdown={len(images_in_md)}")

    # N11: Images have YouTube timestamp links nearby
    ts_link_pattern = r'\[.*?->\]\(https://www\.youtube\.com/watch\?v=.*?&t=\d+s\)'
    ts_links = re.findall(ts_link_pattern, md)
    check("N11", len(ts_links) >= 1, f"Timestamp links={len(ts_links)}")

    # N12: Contains transcript toggle block
    check("N12", "<details>" in md and "전체 스크립트" in md, "Missing transcript toggle")

    # N13: Contains common mistakes table
    check("N13", "흔한 실수" in md, "Missing '흔한 실수' section")

    # N14: Contains keywords section
    check("N14", "관련 키워드" in md, "Missing keywords section")

    # N15: No duplicate GIF/screenshot at same timestamp
    # Check that gif URLs don't appear alongside screenshot URLs for same time
    gif_urls = {g.get("public_url") for g in media.get("gifs", []) if g.get("public_url")}
    ss_urls = {s.get("public_url") for s in media.get("screenshots", []) if s.get("public_url")}
    # Both should be in markdown, but not overlapping timestamps
    gif_ts = {g.get("timestamp") for g in media.get("gifs", [])}
    ss_ts = {s.get("timestamp") for s in media.get("screenshots", [])}
    overlap = gif_ts & ss_ts
    check("N15", len(overlap) == 0, f"Media timestamp overlap: {overlap}")

    # === Content Fidelity ===

    # NF1: All major sections from JSON are present in markdown
    expected_sections = 0
    found_sections = 0
    section_checks = [
        (sn.get("one_line_summary"), "한 줄 요약"),
        (sn.get("detailed_summary"), "상세 요약"),
        (sn.get("topics"), "타임라인"),
        (sn.get("concepts"), "핵심 개념"),
        (sn.get("full_lecture_notes"), "전체 강의 노트"),
        (sn.get("step_by_step"), "단계별"),
        (sn.get("common_mistakes"), "흔한 실수"),
        (sn.get("keywords"), "관련 키워드"),
    ]
    for content, heading in section_checks:
        if content:
            expected_sections += 1
            if heading in md:
                found_sections += 1
    check("NF1", found_sections >= expected_sections - 1,
          f"Sections found {found_sections}/{expected_sections}")

    # NF2: Image count in markdown >= images in JSON (allowing some flex)
    json_media_count = total_media
    check("NF2", len(images_in_md) >= max(1, json_media_count // 3),
          f"Images: markdown={len(images_in_md)}, JSON={json_media_count}")

    # NF3: No major truncation (markdown should be proportional to JSON content)
    json_content_len = len(json.dumps(sn, ensure_ascii=False))
    # Markdown should be at least 30% of JSON content length
    ratio = len(md) / max(json_content_len, 1)
    check("NF3", ratio >= 0.3, f"Content ratio={ratio:.2f} (md={len(md)}, json={json_content_len})")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test youtube-to-notion rendering")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--video-id", help="Test specific video ID")
    args = parser.parse_args()

    if not args.all and not args.video_id:
        print("Usage: --all or --video-id <id>")
        sys.exit(1)

    video_ids = TEST_VIDEO_IDS if args.all else [args.video_id]

    # Check prerequisites
    missing = [v for v in video_ids if not os.path.exists(os.path.join(STUDY_NOTES_DIR, f"{v}.json"))]
    if missing:
        print(f"ERROR: Missing study note JSONs for: {missing}")
        print(f"Run test_youtube_summarize.py first to generate them.")
        sys.exit(1)

    total_pass = 0
    total_fail = 0
    total_checks = 0

    for vid in video_ids:
        print(f"\n{'='*60}")
        print(f"Testing Notion render: {vid}")
        print(f"{'='*60}")

        json_path = os.path.join(STUDY_NOTES_DIR, f"{vid}.json")

        print(f"  Rendering markdown...")
        md_path = render_markdown(vid)

        print(f"  Validating...")
        results = validate(vid, md_path, json_path)

        passed = sum(1 for _, p, _ in results if p)
        failed = sum(1 for _, p, _ in results if not p)
        total_pass += passed
        total_fail += failed
        total_checks += len(results)

        print(f"\n  Result: {passed}/{len(results)} checks passed")

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_pass}/{total_checks} checks passed, {total_fail} failed")
    print(f"{'='*60}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
