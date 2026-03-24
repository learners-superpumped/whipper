#!/usr/bin/env python3
"""
Render a study note JSON into Notion-flavored markdown.
Usage: python render_notion_md.py /tmp/yt_study_notes/<video_id>.json [--output /tmp/notion_md.md]
"""

import argparse
import json
import os
import sys


def format_timestamp_link(video_url: str, timestamp: int, label: str = "") -> str:
    """Create a YouTube timestamp link."""
    mm = timestamp // 60
    ss = timestamp % 60
    ts_str = f"{mm:02d}:{ss:02d}"
    if not label:
        label = f"영상에서 이 장면 보기 ({ts_str})"
    return f"[{label} ->]({video_url}&t={timestamp}s)"


def render_study_note_to_notion_md(data: dict) -> str:
    """Convert study note JSON to Notion markdown string."""
    meta = data.get("meta", {})
    sn = data.get("study_note", {})
    media = data.get("media", {})
    transcript = data.get("transcript", {})

    video_url = meta.get("video_url", "")
    lines = []

    # Header
    lines.append(f"> [YouTube에서 보기]({video_url})")
    view_count = meta.get("view_count", 0)
    duration = meta.get("duration", 0)
    dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"
    upload_date = meta.get("upload_date", "N/A")
    analysis = meta.get("analysis_mode", "gemini")
    lines.append(f"> 조회수: {view_count:,} | 길이: {dur_str} | 업로드: {upload_date} | 분석: {analysis}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # One-line summary
    if sn.get("one_line_summary"):
        lines.append("## 한 줄 요약")
        lines.append(sn["one_line_summary"])
        lines.append("")

    # Detailed summary
    if sn.get("detailed_summary"):
        lines.append("## 상세 요약")
        lines.append(sn["detailed_summary"])
        lines.append("")

    # Audience & difficulty
    if sn.get("target_audience") or sn.get("difficulty_level"):
        lines.append("## 대상 & 난이도")
        if sn.get("target_audience"):
            lines.append(f"- **대상**: {sn['target_audience']}")
        if sn.get("difficulty_level"):
            lines.append(f"- **난이도**: {sn['difficulty_level']}")
        if sn.get("prerequisites"):
            lines.append(f"- **사전 지식**: {sn['prerequisites']}")
        lines.append("")

    # Timeline
    topics = sn.get("topics", [])
    if topics:
        lines.append("## 타임라인 (주제별 구간)")
        lines.append("| 시간 | 주제 | 핵심 내용 |")
        lines.append("|------|------|-----------|")
        for t in topics:
            tr = t.get("timestamp_range", "")
            topic = t.get("topic", "")
            desc = t.get("description", "").replace("\n", " ")[:200]
            lines.append(f"| {tr} | {topic} | {desc} |")
        lines.append("")

    # Key concepts
    concepts = sn.get("concepts", [])
    if concepts:
        lines.append("## 핵심 개념 사전")
        for c in concepts:
            term = c.get("term", "")
            definition = c.get("definition", "")
            why = c.get("why_important", "")
            analogy = c.get("analogy", "")
            app = c.get("practical_application", "")
            lines.append(f"- **{term}**: {definition}")
            if why:
                lines.append(f"  - 왜 중요한가: {why}")
            if analogy:
                lines.append(f"  - 비유/예시: *\"{analogy}\"*")
            if app:
                lines.append(f"  - 적용: {app}")
        lines.append("")

    # Full lecture notes
    fln = sn.get("full_lecture_notes", [])
    if fln:
        lines.append("## 전체 강의 노트")
        for note in fln:
            title = note.get("section_title", "")
            tr = note.get("timestamp_range", "")
            content = note.get("content", "")
            lines.append(f"### {title} ({tr})")
            lines.append(content)
            lines.append("")

    # Step-by-step
    steps = sn.get("step_by_step", [])
    if steps:
        lines.append("## 단계별 실습 가이드")
        for s in steps:
            step_num = s.get("step", "")
            title = s.get("title", "")
            lines.append(f"### Step {step_num}: {title}")
            for field, label in [
                ("preparation", "준비"),
                ("body_position", "자세/위치"),
                ("method", "방법"),
                ("intensity_timing", "강도/타이밍"),
                ("success_criteria", "성공 기준"),
                ("failure_adjustment", "실패 시 조정"),
                ("warnings", "주의사항"),
                ("frequency", "빈도"),
            ]:
                val = s.get(field, "")
                if val:
                    lines.append(f"- **{label}**: {val}")
            ts = s.get("timestamp", "")
            if ts and video_url:
                import re
                m = re.match(r'(\d+):(\d+)', ts)
                if m:
                    sec = int(m.group(1)) * 60 + int(m.group(2))
                    lines.append(f"- {format_timestamp_link(video_url, sec, f'영상에서 보기 ({ts})')}")
            lines.append("")

    # Demonstrations with media
    demos = sn.get("demonstrations", [])
    if demos:
        lines.append("## 시연 장면 기록")
        # Build media lookup by timestamp
        gif_ts_map = {g.get("timestamp"): g for g in media.get("gifs", [])}
        ss_ts_map = {s.get("timestamp"): s for s in media.get("screenshots", [])}

        for d in demos:
            title = d.get("title", "")
            ts_str = d.get("timestamp", "")
            lines.append(f"### {title} ({ts_str})")

            # Try to find matching media
            import re
            m = re.match(r'(\d+):(\d+)', ts_str)
            if m:
                sec = int(m.group(1)) * 60 + int(m.group(2))
                # Check GIF first
                gif = gif_ts_map.get(sec)
                if gif and gif.get("public_url"):
                    lines.append(f"![{ts_str} - {title}]({gif['public_url']})")
                    lines.append(format_timestamp_link(video_url, sec))
                    lines.append("")
                else:
                    # Check screenshot (within ±30 sec range)
                    closest_ss = None
                    min_diff = 31
                    for ss_sec, ss_data in ss_ts_map.items():
                        diff = abs(ss_sec - sec)
                        if diff < min_diff:
                            min_diff = diff
                            closest_ss = ss_data
                    if closest_ss and closest_ss.get("public_url"):
                        lines.append(f"![{ts_str} - {title}]({closest_ss['public_url']})")
                        lines.append(format_timestamp_link(video_url, sec))
                        lines.append("")

            for field, label in [
                ("situation", "상황"),
                ("instructor_action", "강사 동작"),
                ("subject_reaction", "대상 반응"),
                ("learner_attempt", "학습자 시도"),
                ("instructor_comment", "강사 코멘트"),
                ("visual_detail", "화면 정보"),
            ]:
                val = d.get(field, "")
                if val:
                    lines.append(f"- **{label}**: {val}")
            lines.append("")

    # Common mistakes
    mistakes = sn.get("common_mistakes", [])
    if mistakes:
        lines.append("## 흔한 실수 & 오해")
        lines.append("| 실수/오해 | 왜 문제인가 | 올바른 방법 |")
        lines.append("|-----------|-----------|------------|")
        for m in mistakes:
            mistake = m.get("mistake", "").replace("\n", " ")
            why = m.get("why_problem", "").replace("\n", " ")
            correction = m.get("correction", "").replace("\n", " ")
            lines.append(f"| {mistake} | {why} | {correction} |")
        lines.append("")

    # Q&A
    qa = sn.get("qa_from_video", [])
    if qa:
        lines.append("## Q&A")
        for item in qa:
            q = item.get("question", "")
            a = item.get("answer", "")
            lines.append(f"- **Q**: {q}")
            lines.append(f"  **A**: {a}")
        lines.append("")

    # Quotes
    quotes = sn.get("quotes", [])
    if quotes:
        lines.append("## 인용 & 명언")
        for q in quotes:
            quote = q.get("quote", "")
            context = q.get("context", "")
            lines.append(f"- *\"{quote}\"* — {context}")
        lines.append("")

    # Keywords
    keywords = sn.get("keywords", [])
    if keywords:
        lines.append("## 관련 키워드")
        lines.append(" ".join(f"`{k}`" for k in keywords))
        lines.append("")

    # Remaining screenshots (not used in demos)
    used_urls = set()
    for d in demos:
        import re
        m = re.match(r'(\d+):(\d+)', d.get("timestamp", ""))
        # just track that demos may have used some media

    remaining_ss = [s for s in media.get("screenshots", []) if s.get("public_url")]
    if remaining_ss:
        lines.append("## 화면 캡처")
        for s in remaining_ss[:6]:
            ts = s.get("timestamp", 0)
            ts_fmt = s.get("timestamp_formatted", "")
            url = s.get("public_url", "")
            if url:
                lines.append(f"![{ts_fmt}]({url})")
                lines.append(format_timestamp_link(video_url, ts, f"영상에서 보기 ({ts_fmt})"))
                lines.append("")

    # Full transcript in toggle
    lines.append("---")
    lines.append("")
    full_text = transcript.get("full_text", "")
    if full_text:
        lines.append("<details>")
        lines.append("<summary>전체 스크립트 (원문)</summary>")
        lines.append("")
        # Split long transcript into chunks to avoid Notion limits
        chunk_size = 8000
        for i in range(0, len(full_text), chunk_size):
            lines.append(full_text[i:i + chunk_size])
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render study note to Notion markdown")
    parser.add_argument("input_file", help="Study note JSON file")
    parser.add_argument("--output", help="Output markdown file (defaults to stdout)")
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
