#!/usr/bin/env bash
# Usage: post.sh <task_dir> <channel> <thread_ts> <text>
# Writes a .json file to {task_dir}/slack_messages/ for the bridge to pick up.

TASK_DIR="$1"
CHANNEL="$2"
THREAD_TS="$3"
TEXT="$4"

if [ -z "$TASK_DIR" ] || [ -z "$TEXT" ]; then
  echo "Usage: post.sh <task_dir> <channel> <thread_ts> <text>" >&2
  exit 1
fi

MSG_DIR="${TASK_DIR}/slack_messages"
mkdir -p "$MSG_DIR"

TIMESTAMP=$(python3 -c "import time; print(f'{time.time():.6f}')")
cat > "${MSG_DIR}/${TIMESTAMP}.json" << JSONEOF
{"text": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$TEXT"), "channel": "$CHANNEL", "thread_ts": "$THREAD_TS"}
JSONEOF
