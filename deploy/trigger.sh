#!/usr/bin/env bash
set -euo pipefail

HOST_REPO_DIR="${YOUTUBE_BOT_HOST_REPO_DIR:-/home/natuki/services/discord-bots/youtube-bot}"
DEPLOY_IMAGE="${YOUTUBE_BOT_DEPLOY_IMAGE:-web-server-deploy}"
RUNNER_NAME="youtube-bot-deployer"

if docker inspect "${RUNNER_NAME}" >/dev/null 2>&1; then
  if [ "$(docker inspect --format '{{.State.Running}}' "${RUNNER_NAME}")" = "true" ]; then
    echo "A deployment is already running."
    exit 0
  fi

  docker rm "${RUNNER_NAME}" >/dev/null
fi

docker run --detach \
  --name "${RUNNER_NAME}" \
  --env DEPLOY_UID=1000 \
  --env DEPLOY_GID=1000 \
  --volume "${HOST_REPO_DIR}:/youtube-bot:rw" \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --entrypoint /youtube-bot/deploy/deploy.sh \
  "${DEPLOY_IMAGE}" >/dev/null

echo "Deployment accepted."
