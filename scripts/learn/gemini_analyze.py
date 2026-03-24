#!/usr/bin/env python3
"""
Analyze YouTube video using Google Gemini API with video input.
Downloads the video and sends it to Gemini for structured analysis.

Usage:
  python gemini_analyze.py <video_url> --video-id <id> --output /tmp/gemini_results/

Requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time


def download_video(video_url: str, output_path: str) -> bool:
    """Download video at medium quality for Gemini analysis."""
    cmd = [
        "yt-dlp",
        "-f", "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best",
        "--no-warnings",
        "--max-filesize", "200M",
        "-o", output_path,
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result.returncode == 0 and os.path.exists(output_path)


def analyze_with_gemini(video_path: str, title: str, language_hint: str = "ko") -> dict:
    """Send video to Gemini and get structured analysis."""
    try:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return {"success": False, "error": "GEMINI_API_KEY or GOOGLE_API_KEY not set"}

        client = genai.Client(api_key=api_key)

        # Upload video file
        print("Uploading video to Gemini...", file=sys.stderr)
        video_file = client.files.upload(file=video_path)

        # Wait for processing
        print("Waiting for video processing...", file=sys.stderr)
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            return {"success": False, "error": "Video processing failed"}

        print("Analyzing with Gemini...", file=sys.stderr)

        lang_instruction = ""
        if language_hint == "en":
            lang_instruction = "The video is in English. Write ALL analysis in Korean, but include original English verbatim for quotes."
        else:
            lang_instruction = "Write in Korean."

        prompt = f"""Analyze this YouTube video completely and exhaustively, structuring it as comprehensive study notes. Title: "{title}"

Core principle: Write detailed enough that someone can understand ALL content without watching the video. This is NOT a summary — it is a complete reconstruction of everything said, shown, and demonstrated. Record every tip, every demonstration, every warning, every analogy.

{lang_instruction}

Output as valid JSON in this format:

{{
  "one_line_summary": "Single sentence core message",
  "detailed_summary": "5-8 sentences. Background, participants, situation, core message, problems addressed, solutions presented, conclusion. Why this video exists, who it helps, what you can do after watching.",
  "target_audience": "Specific audience description",
  "difficulty_level": "Beginner/Intermediate/Advanced",
  "prerequisites": "Prior knowledge needed (empty string if none)",
  "topics": [
    {{"topic": "Topic name", "description": "2-3 sentences describing what's covered in this segment in detail. What the speaker specifically explains and demonstrates.", "timestamp_range": "MM:SS-MM:SS"}}
  ],
  "concepts": [
    {{"term": "Concept/term name", "definition": "Definition", "why_important": "Why it matters", "analogy": "Original analogy/metaphor used in the video (verbatim)", "practical_application": "How it's applied in the video"}}
  ],
  IMPORTANT: concepts MUST have at least 6 entries. Include every distinct concept, technique, and term mentioned in the video.
  "full_lecture_notes": [
    {{"section_title": "Section title", "timestamp_range": "MM:SS-MM:SS", "content": "Detailed description of everything the speaker said and did in this segment. What the situation was, what they said (quote key statements verbatim), what they demonstrated (describe movements/posture/tools/reactions specifically), why they did it that way, what instructions they gave the learner, how the subject responded. Minimum 5 sentences, 10+ for content-heavy segments."}}
  ],
  "step_by_step": [
    {{"step": 1, "title": "Step title", "preparation": "What you need", "body_position": "Exact positions, hand placement, body angles — not 'put your hand in' but 'insert index and middle fingers on both sides of the collar, place thumb on the protruding bone between the eye and ear canal'", "method": "Specific how-to, step by step", "intensity_timing": "How hard, how long, when", "success_criteria": "What response indicates success", "failure_adjustment": "How to adjust if it doesn't work", "warnings": "What you must NEVER do", "frequency": "How often, for how many days", "timestamp": "MM:SS"}}
  ],
  "demonstrations": [
    {{"title": "Demo title", "timestamp": "MM:SS", "situation": "Context of the demonstration", "instructor_action": "Exactly what movements were made — not 'did a technique' but 'bent knees slightly, leaned upper body forward like a wall, used thighs and shins to push the space, moving the subject 2 steps backward'", "subject_reaction": "Before/during/after reactions", "learner_attempt": "Differences when learner tried, correction points given", "instructor_comment": "Explanation given during demonstration", "visual_detail": "Visual information only visible on screen (posture, angles, tool positions)"}}
  ],
  "common_mistakes": [
    {{"mistake": "Specific mistake", "why_problem": "Detailed reason why it's problematic", "correction": "Specific correction method", "example_from_video": "Situation/example mentioned in video"}}
  ],
  "qa_from_video": [
    {{"question": "Question asked (verbatim)", "answer": "Detailed answer given", "timestamp": "MM:SS"}}
  ],
  "quotes": [
    {{"quote": "Notable verbatim quote from the speaker", "context": "Situation and meaning", "timestamp": "MM:SS"}}
  ],
  "visual_key_moments": [
    {{"timestamp": "MM:SS", "description": "Important visual information NOT in audio/subtitles. Physical movements, tool usage, posture, angles visible only on screen."}}
  ],
  "keywords": ["keyword1", "keyword2"]
}}

Critical instructions:
- full_lecture_notes is the MOST IMPORTANT field. Describe ALL video content chronologically, leaving nothing out. Reading this alone should equal watching the entire video.
- Each full_lecture_notes content: minimum 5 sentences, 10+ for dense segments.
- demonstrations instructor_action: describe physical movements at maximum detail level.
- Preserve all analogies/metaphors verbatim in concepts.analogy.
- step_by_step body_position: exact physical descriptions, not vague instructions. Each field (preparation, body_position, method, warnings) should be at least 30 characters for specificity.
- step_by_step: include ALL distinct steps/techniques taught. Minimum 3 steps.
- qa_from_video: ALL questions asked and answers given in the video.
- visual_key_moments: information ONLY visible on screen, not in audio.
- Timestamps must be as accurate as possible to the actual video time."""

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[video_file, prompt],
            config={"max_output_tokens": 65536},
        )

        # Parse JSON from response
        text = response.text.strip()
        # Remove markdown code fence if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            elif "```" in text:
                text = text[:text.rfind("```")]
        text = text.strip()

        result = json.loads(text)
        result["success"] = True

        # Clean up uploaded file
        try:
            client.files.delete(name=video_file.name)
        except Exception:
            pass

        return result

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON parse error: {e}", "raw_text": text[:2000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Analyze YouTube video with Gemini")
    parser.add_argument("video_url", help="YouTube video URL")
    parser.add_argument("--video-id", default="video", help="Video ID")
    parser.add_argument("--title", default="", help="Video title")
    parser.add_argument("--language", default="ko", help="Expected language (ko/en)")
    parser.add_argument("--output", default="/tmp/gemini_results", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, f"{args.video_id}.mp4")

        print(f"Downloading: {args.title or args.video_url}", file=sys.stderr)
        if not download_video(args.video_url, video_path):
            # Check for other formats
            found = False
            for ext in ["webm", "mkv"]:
                alt = os.path.join(tmpdir, f"{args.video_id}.{ext}")
                if os.path.exists(alt):
                    video_path = alt
                    found = True
                    break
            if not found:
                print("Download failed", file=sys.stderr)
                result = {"success": False, "error": "Download failed"}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                sys.exit(1)

        result = analyze_with_gemini(video_path, args.title, args.language)

    # Save result
    output_file = os.path.join(args.output, f"{args.video_id}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
