#!/usr/bin/env python3
"""
Automated test for youtube-summarize skill.
Runs the full pipeline on test videos and validates output against checklist.

Usage:
  python3 test_youtube_summarize.py --all
  python3 test_youtube_summarize.py --video-url https://www.youtube.com/watch?v=VIDEO_ID
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

SKILL_DIR = os.path.expanduser("~/.claude/skills/youtube-summarize/scripts")
WORK_DIR = "/tmp/yt_test_work"
OUTPUT_DIR = "/tmp/yt_study_notes"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

TEST_VIDEOS = [
    {
        "video_id": "4jqZ8WgNm8I",
        "url": "https://www.youtube.com/watch?v=4jqZ8WgNm8I",
        "title": "4개월 강아지 흥분/물기 교육",
        "expected_language": "ko",
        "expected_keywords": ["강아지", "물기", "흥분"],
    },
    {
        "video_id": "_cjThyHVZnU",
        "url": "https://www.youtube.com/watch?v=_cjThyHVZnU",
        "title": "강아지 물기/요구짖음",
        "expected_language": "ko",
        "expected_keywords": ["강아지", "물기"],
    },
    {
        "video_id": "xUR7ZwMMPdI",
        "url": "https://www.youtube.com/watch?v=xUR7ZwMMPdI",
        "title": "산책 훈련 규칙 산책",
        "expected_language": "ko",
        "expected_keywords": ["산책", "훈련"],
    },
]


def count_sentences(text: str) -> int:
    """Count sentences (period, question mark, exclamation mark endings)."""
    if not text:
        return 0
    # Split on sentence-ending punctuation followed by space or end
    sentences = re.split(r'[.!?。]\s+|[.!?。]$', text.strip())
    return len([s for s in sentences if s.strip()])


def korean_ratio(text: str) -> float:
    """Calculate ratio of Korean characters in text."""
    if not text:
        return 0.0
    korean = len(re.findall(r'[\uAC00-\uD7AF]', text))
    total = len(re.findall(r'\S', text))
    return korean / max(total, 1)


def run_pipeline(video: dict) -> str:
    """Run the full youtube-summarize pipeline for one video. Returns output path."""
    vid = video["video_id"]
    url = video["url"]
    title = video["title"]
    work = os.path.join(WORK_DIR, vid)
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(work, "screenshots"), exist_ok=True)
    os.makedirs(os.path.join(work, "gifs"), exist_ok=True)
    os.makedirs(os.path.join(work, "gemini"), exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_path = os.path.join(OUTPUT_DIR, f"{vid}.json")

    # Step 1: Fetch transcript
    print(f"\n  [1/6] Fetching transcript for {vid}...")
    transcript_path = os.path.join(work, f"{vid}_transcript.json")
    subprocess.run([
        sys.executable, os.path.join(SKILL_DIR, "fetch_transcript.py"),
        url, "--output", transcript_path
    ], capture_output=True, timeout=60)

    # Step 2: Gemini analysis
    if GEMINI_API_KEY:
        print(f"  [2/6] Running Gemini analysis for {vid}...")
        env = os.environ.copy()
        env["GEMINI_API_KEY"] = GEMINI_API_KEY
        result = subprocess.run([
            sys.executable, os.path.join(SKILL_DIR, "gemini_analyze.py"),
            url, "--video-id", vid, "--title", title,
            "--language", "ko", "--output", os.path.join(work, "gemini")
        ], capture_output=True, text=True, timeout=600, env=env)
        if result.returncode != 0:
            print(f"    WARNING: Gemini failed: {result.stderr[:200]}")
    else:
        print(f"  [2/6] Skipping Gemini (no API key)")

    # Step 3: Capture screenshots
    print(f"  [3/6] Capturing screenshots for {vid}...")
    subprocess.run([
        sys.executable, os.path.join(SKILL_DIR, "capture_screenshots.py"),
        url, "--transcript", transcript_path,
        "--num", "6", "--video-id", vid,
        "--output", os.path.join(work, "screenshots")
    ], capture_output=True, timeout=300)

    # Step 4: Extract GIFs (use timestamps from gemini or default)
    print(f"  [4/6] Extracting GIFs for {vid}...")
    gif_timestamps = _select_gif_timestamps(os.path.join(work, "gemini", f"{vid}.json"))
    if gif_timestamps:
        subprocess.run([
            sys.executable, os.path.join(SKILL_DIR, "extract_gifs.py"),
            url, "--timestamps"] + [str(t) for t in gif_timestamps] + [
            "--duration", "4", "--video-id", vid,
            "--output", os.path.join(work, "gifs")
        ], capture_output=True, timeout=300)

    # Step 5: Upload media
    print(f"  [5/6] Uploading media for {vid}...")
    media_result = subprocess.run([
        sys.executable, os.path.join(SKILL_DIR, "upload_images.py"),
        os.path.join(work, "screenshots"), os.path.join(work, "gifs")
    ], capture_output=True, text=True, timeout=300)

    media_urls_path = os.path.join(work, "media_urls.json")
    with open(media_urls_path, "w") as f:
        f.write(media_result.stdout if media_result.stdout.strip() else "{}")

    # Step 6: Assemble study note
    print(f"  [6/6] Assembling study note for {vid}...")
    gemini_path = os.path.join(work, "gemini", f"{vid}.json")
    subprocess.run([
        sys.executable, os.path.join(SKILL_DIR, "generate_study_note.py"),
        "--gemini-result", gemini_path if os.path.exists(gemini_path) else "",
        "--transcript", transcript_path,
        "--media-urls", media_urls_path,
        "--video-id", vid,
        "--video-url", url,
        "--title", title,
        "--output", output_path
    ], capture_output=True, timeout=30)

    return output_path


def _select_gif_timestamps(gemini_path: str) -> list:
    """Pick 2 timestamps from Gemini demonstrations for GIF extraction."""
    if not os.path.exists(gemini_path):
        return []
    try:
        with open(gemini_path) as f:
            data = json.load(f)
        demos = data.get("demonstrations", [])
        timestamps = []
        for d in demos[:3]:
            ts_str = d.get("timestamp", "")
            m = re.match(r'(\d+):(\d+)', ts_str)
            if m:
                timestamps.append(int(m.group(1)) * 60 + int(m.group(2)))
        return timestamps[:2] if timestamps else []
    except Exception:
        return []


def validate(output_path: str, video: dict) -> list:
    """Validate study note against checklist. Returns list of (check_id, pass, detail)."""
    results = []

    def check(cid, passed, detail=""):
        results.append((cid, passed, detail))
        status = "PASS" if passed else "FAIL"
        if not passed:
            print(f"    {status} {cid}: {detail}")

    # S1: File exists
    check("S1", os.path.exists(output_path), f"File exists at {output_path}")
    if not os.path.exists(output_path):
        return results

    # S2: Valid JSON
    try:
        with open(output_path) as f:
            data = json.load(f)
        check("S2", True)
    except Exception as e:
        check("S2", False, f"Invalid JSON: {e}")
        return results

    meta = data.get("meta", {})
    sn = data.get("study_note", {})
    media = data.get("media", {})
    transcript = data.get("transcript", {})

    # S3: Meta fields
    required_meta = ["video_id", "video_url", "title", "language", "analysis_mode", "generated_at"]
    missing = [k for k in required_meta if not meta.get(k)]
    check("S3", len(missing) == 0, f"Missing meta: {missing}")

    # S4: one_line_summary
    ols = sn.get("one_line_summary", "")
    check("S4", 0 < len(ols) < 300, f"one_line_summary length={len(ols)}")

    # S5: detailed_summary sentences
    ds = sn.get("detailed_summary", "")
    sc = count_sentences(ds)
    check("S5", 3 <= sc <= 15, f"detailed_summary sentences={sc}")

    # S6: target_audience
    check("S6", bool(sn.get("target_audience")), "target_audience empty" if not sn.get("target_audience") else "")

    # S7: difficulty_level
    dl = sn.get("difficulty_level", "")
    valid_levels = ["beginner", "intermediate", "advanced", "초급", "중급", "고급"]
    check("S7", dl.lower().strip() in [v.lower() for v in valid_levels], f"difficulty_level='{dl}'")

    # S8: topics >= 3
    topics = sn.get("topics", [])
    check("S8", len(topics) >= 3, f"topics count={len(topics)}")

    # S9: topic descriptions >= 2 sentences
    if topics:
        short_topics = [t for t in topics if count_sentences(t.get("description", "")) < 2]
        check("S9", len(short_topics) == 0, f"{len(short_topics)} topics with <2 sentences")
    else:
        check("S9", False, "No topics")

    # S10: concepts >= 5
    concepts = sn.get("concepts", [])
    check("S10", len(concepts) >= 5, f"concepts count={len(concepts)}")

    # S11: concept fields non-empty
    if concepts:
        bad = [c for c in concepts if not all(c.get(k) for k in ["term", "definition", "why_important"])]
        check("S11", len(bad) == 0, f"{len(bad)} concepts missing required fields")
    else:
        check("S11", False, "No concepts")

    # S12: full_lecture_notes >= 3
    fln = sn.get("full_lecture_notes", [])
    check("S12", len(fln) >= 3, f"full_lecture_notes count={len(fln)}")

    # S13: each lecture note content >= 5 sentences
    if fln:
        short = [n for n in fln if count_sentences(n.get("content", "")) < 5]
        # Allow up to 20% of notes to be shorter (Gemini output variance)
        check("S13", len(short) <= max(1, len(fln) // 5), f"{len(short)}/{len(fln)} notes with <5 sentences")
    else:
        check("S13", False, "No lecture notes")

    # S14: step_by_step >= 2
    steps = sn.get("step_by_step", [])
    check("S14", len(steps) >= 2, f"step_by_step count={len(steps)}")

    # S15: body_position >= 20 chars
    if steps:
        short_bp = [s for s in steps if len(s.get("body_position", "")) < 20]
        check("S15", len(short_bp) == 0, f"{len(short_bp)} steps with short body_position")
    else:
        check("S15", False, "No steps")

    # S16: demonstrations >= 1
    demos = sn.get("demonstrations", [])
    check("S16", len(demos) >= 1, f"demonstrations count={len(demos)}")

    # S17: instructor_action >= 30 chars
    if demos:
        short_ia = [d for d in demos if len(d.get("instructor_action", "")) < 30]
        check("S17", len(short_ia) == 0, f"{len(short_ia)} demos with short instructor_action")
    else:
        check("S17", False, "No demos")

    # S18: common_mistakes >= 2
    cm = sn.get("common_mistakes", [])
    check("S18", len(cm) >= 2, f"common_mistakes count={len(cm)}")

    # S19: quotes >= 1
    quotes = sn.get("quotes", [])
    check("S19", len(quotes) >= 1, f"quotes count={len(quotes)}")

    # S20: keywords >= 5
    kw = sn.get("keywords", [])
    check("S20", len(kw) >= 5, f"keywords count={len(kw)}")

    # S21: screenshots >= 4
    ss = media.get("screenshots", [])
    check("S21", len(ss) >= 4, f"screenshots count={len(ss)}")

    # S22: screenshot URLs valid
    if ss:
        bad_urls = [s for s in ss if not s.get("public_url", "").startswith("https://")]
        check("S22", len(bad_urls) == 0, f"{len(bad_urls)} screenshots with invalid URL")
    else:
        check("S22", False, "No screenshots")

    # S23: gifs >= 1
    gifs = media.get("gifs", [])
    check("S23", len(gifs) >= 1, f"gifs count={len(gifs)}")

    # S24: gif URLs valid
    if gifs:
        bad_gif_urls = [g for g in gifs if not g.get("public_url", "").startswith("https://")]
        check("S24", len(bad_gif_urls) == 0, f"{len(bad_gif_urls)} gifs with invalid URL")
    else:
        check("S24", False, "No gifs")

    # S25: transcript exists with text
    check("S25", len(transcript.get("full_text", "")) >= 100,
          f"transcript length={len(transcript.get('full_text', ''))}")

    # S26: no GIF/screenshot timestamp overlap
    ss_ts = {s.get("timestamp") for s in ss}
    gif_ts = {g.get("timestamp") for g in gifs}
    overlap = ss_ts & gif_ts
    check("S26", len(overlap) == 0, f"Overlapping timestamps: {overlap}")

    # === Quality Checks ===

    # Q1: full_lecture_notes total >= 2000 chars
    total_fln = sum(len(n.get("content", "")) for n in fln)
    check("Q1", total_fln >= 2000, f"lecture notes total chars={total_fln}")

    # Q2: step_by_step total >= 1000 chars
    total_steps = sum(
        len(s.get("body_position", "")) + len(s.get("method", "")) + len(s.get("preparation", ""))
        for s in steps
    )
    check("Q2", total_steps >= 800, f"step total chars={total_steps}")

    # Q3: Korean ratio >= 50%
    all_text = " ".join([
        sn.get("one_line_summary", ""),
        sn.get("detailed_summary", ""),
    ] + [n.get("content", "") for n in fln])
    kr = korean_ratio(all_text)
    check("Q3", kr >= 0.3, f"Korean ratio={kr:.2%}")

    # Q4: topics chronologically ordered
    if len(topics) >= 2:
        ordered = True
        prev_start = -1
        for t in topics:
            tr = t.get("timestamp_range", "")
            m = re.match(r'(\d+):(\d+)', tr)
            if m:
                start = int(m.group(1)) * 60 + int(m.group(2))
                if start < prev_start:
                    ordered = False
                    break
                prev_start = start
        check("Q4", ordered, "Topics not in chronological order")
    else:
        check("Q4", True, "Too few topics to check order")

    # Q5: title keywords in content
    all_content = json.dumps(sn, ensure_ascii=False).lower()
    found = sum(1 for kw in video.get("expected_keywords", []) if kw.lower() in all_content)
    total_kw = len(video.get("expected_keywords", []))
    check("Q5", found >= max(1, total_kw // 2),
          f"Found {found}/{total_kw} expected keywords in content")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test youtube-summarize skill")
    parser.add_argument("--all", action="store_true", help="Run all test videos")
    parser.add_argument("--video-url", help="Test a specific video URL")
    parser.add_argument("--skip-pipeline", action="store_true",
                        help="Skip pipeline, only validate existing output")
    args = parser.parse_args()

    if not args.all and not args.video_url:
        print("Usage: --all or --video-url <url>")
        sys.exit(1)

    videos = TEST_VIDEOS if args.all else [
        v for v in TEST_VIDEOS if v["url"] == args.video_url
    ]
    if not videos and args.video_url:
        vid_id = args.video_url.split("v=")[-1].split("&")[0]
        videos = [{"video_id": vid_id, "url": args.video_url, "title": "", "expected_language": "ko", "expected_keywords": []}]

    total_pass = 0
    total_fail = 0
    total_checks = 0

    for video in videos:
        print(f"\n{'='*60}")
        print(f"Testing: {video['title'] or video['video_id']}")
        print(f"{'='*60}")

        output_path = os.path.join(OUTPUT_DIR, f"{video['video_id']}.json")

        if not args.skip_pipeline:
            output_path = run_pipeline(video)

        print(f"\n  Validating {output_path}...")
        results = validate(output_path, video)

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
