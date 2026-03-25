#!/usr/bin/env python3
"""Render and install the Whipper launch agent plist for the current machine."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT_DIR / "scripts" / "daemon" / "com.whipper.daemon.plist"
TARGET_PATH = Path.home() / "Library" / "LaunchAgents" / "com.whipper.daemon.plist"


def render_plist(python_bin: str, repo_root: str, path_env: str) -> str:
    template = TEMPLATE_PATH.read_text()
    return (
        template.replace("__PYTHON_BIN__", python_bin)
        .replace("__WHIPPER_ROOT__", repo_root)
        .replace("__PATH__", path_env)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--repo-root", default=str(ROOT_DIR))
    parser.add_argument("--path-env", default=os.environ.get("PATH", ""))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(
        render_plist(args.python_bin, args.repo_root, args.path_env)
    )
    print(f"Wrote {TARGET_PATH}")

    if args.reload:
        label = f"gui/{os.getuid()}/com.whipper.daemon"
        subprocess.run(["launchctl", "bootout", label], check=False)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(TARGET_PATH)], check=True)
        subprocess.run(["launchctl", "kickstart", "-k", label], check=True)
        print(f"Reloaded {label}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
