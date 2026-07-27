#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${YOUTUBE_BOT_REPO_DIR:-/youtube-bot}"
LOG_FILE="${REPO_DIR}/deploy/deploy.log"

nohup "${REPO_DIR}/deploy/deploy.sh" >>"${LOG_FILE}" 2>&1 </dev/null &
echo "Deployment accepted."
