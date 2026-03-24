#!/usr/bin/env python3
"""Notion 퍼블리시용 콘텐츠 포맷터.

이 모듈은 Notion API를 직접 호출하지 않음.
Claude 세션이 MCP 도구(notion-create-pages, notion-update-page)로 호출.
이 모듈의 역할:
1. /tmp/ 의 작업 결과물을 읽어서 Notion 페이지용 마크다운으로 변환
2. 이미지를 catbox.moe에 업로드하고 URL 반환
"""
import json
import sys
import os
import requests

CATBOX_URL = "https://catbox.moe/user/api.php"
MEDIA_EXTENSIONS = (".jpg", ".png", ".gif", ".pdf", ".webp")
IMAGE_EXTENSIONS = (".jpg", ".png", ".webp", ".gif")


def upload_to_catbox(file_path: str) -> str:
    """파일을 catbox.moe에 업로드하고 URL 반환."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            CATBOX_URL,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
        )
    resp.raise_for_status()
    return resp.text.strip()


def upload_media_files(task_dir: str) -> dict:
    """task_dir/resources/ 내 미디어 파일을 catbox에 업로드. {filename: url} 반환."""
    results = {}
    resources_dir = os.path.join(task_dir, "resources")
    if not os.path.isdir(resources_dir):
        return results
    for fname in sorted(os.listdir(resources_dir)):
        fpath = os.path.join(resources_dir, fname)
        if os.path.isfile(fpath) and fname.lower().endswith(MEDIA_EXTENSIONS):
            try:
                results[fname] = upload_to_catbox(fpath)
            except Exception as e:
                print(f"Warning: upload failed {fname}: {e}", file=sys.stderr)
    return results


def format_for_notion(task_dir: str, media_urls: dict = None) -> str:
    """task_dir의 결과물을 Notion 페이지용 마크다운으로 변환."""
    sections = []

    # 성공기준 (README.md)
    readme = os.path.join(task_dir, "README.md")
    if os.path.isfile(readme):
        with open(readme) as f:
            sections.append(f.read())

    # 최종 산출물 (deliverables/)
    deliverables_dir = os.path.join(task_dir, "deliverables")
    if os.path.isdir(deliverables_dir):
        for fname in sorted(os.listdir(deliverables_dir)):
            fpath = os.path.join(deliverables_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath) as f:
                    sections.append(f"## 결과: {fname}\n\n{f.read()}")

    # 이미지 임베드
    if media_urls:
        img_section = "## 첨부 미디어\n"
        for name, url in media_urls.items():
            if url.endswith(IMAGE_EXTENSIONS):
                img_section += f"\n![{name}]({url})\n"
            else:
                img_section += f"\n[{name}]({url})\n"
        sections.append(img_section)

    # Iteration 히스토리
    iterations_dir = os.path.join(task_dir, "iterations")
    if os.path.isdir(iterations_dir):
        iter_files = sorted(os.listdir(iterations_dir))
        if iter_files:
            history = "## Iteration 히스토리\n"
            for fname in iter_files:
                fpath = os.path.join(iterations_dir, fname)
                if os.path.isfile(fpath):
                    with open(fpath) as f:
                        history += f"\n### {fname}\n\n{f.read()}\n"
            sections.append(history)

    return "\n\n---\n\n".join(sections)


def cleanup_task_dir(task_dir: str):
    """완료된 task_dir 삭제. /tmp/whipper-* 경로만 삭제 (안전장치)."""
    import shutil

    if task_dir.startswith("/tmp/whipper-") and os.path.isdir(task_dir):
        shutil.rmtree(task_dir)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: publisher.py <task_dir> [--upload-media]", file=sys.stderr)
        sys.exit(1)

    task_dir = sys.argv[1]
    media_urls = {}
    if "--upload-media" in sys.argv:
        media_urls = upload_media_files(task_dir)
        print(
            json.dumps({"media_urls": media_urls}, ensure_ascii=False),
            file=sys.stderr,
        )

    content = format_for_notion(task_dir, media_urls)
    print(content)
