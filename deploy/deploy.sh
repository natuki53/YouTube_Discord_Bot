#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${YOUTUBE_BOT_REPO_DIR:-/youtube-bot}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
CONTAINER_NAME="youtube-bot"
READY_LOG_TEXT="としてログインしました"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-45}"
DEPLOY_UID="${DEPLOY_UID:-1000}"
DEPLOY_GID="${DEPLOY_GID:-1000}"
LOCK_FILE="${REPO_DIR}/deploy/.deploy.lock"

repair_ownership() {
  chown -R "${DEPLOY_UID}:${DEPLOY_GID}" "${REPO_DIR}" 2>/dev/null || true
}

finish() {
  status=$?
  trap - EXIT
  set +e

  if [ "${status}" -ne 0 ] && [ -n "${previous_commit:-}" ] && [ -d "${REPO_DIR}/.git" ]; then
    echo "Restoring checkout to ${previous_commit}..."
    git -C "${REPO_DIR}" reset --hard "${previous_commit}"
  fi

  repair_ownership
  exit "${status}"
}
trap finish EXIT

mkdir -p "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Another deployment is already running; this delivery was skipped."
  exit 0
fi

cd "${REPO_DIR}"
git config --global --add safe.directory "${REPO_DIR}" 2>/dev/null || true

if [ ! -f .env ]; then
  echo "ERROR: ${REPO_DIR}/.env is missing."
  exit 1
fi

if [ ! -d .git ]; then
  echo "ERROR: ${REPO_DIR} is not a Git checkout."
  exit 1
fi

previous_commit="$(git rev-parse HEAD)"
previous_image="$(docker inspect --format '{{.Config.Image}}' "${CONTAINER_NAME}" 2>/dev/null || true)"

echo "Fetching origin/main..."
git fetch --prune origin main
target_commit="$(git rev-parse origin/main)"

if [ "${previous_commit}" = "${target_commit}" ]; then
  echo "origin/main is already deployed (${target_commit})."
  exit 0
fi

echo "Updating checkout: ${previous_commit} -> ${target_commit}"
git reset --hard "${target_commit}"

candidate_image="youtube-discord-bot:${target_commit}"
echo "Building ${candidate_image}..."
docker build --pull --tag "${candidate_image}" "${REPO_DIR}"

echo "Starting ${CONTAINER_NAME}..."
if ! BOT_IMAGE="${candidate_image}" docker compose \
  --project-name youtube-discord-bot \
  --file "${COMPOSE_FILE}" \
  up -d --no-build --remove-orphans; then
  if [ -n "${previous_image}" ] && docker image inspect "${previous_image}" >/dev/null 2>&1; then
    echo "Start failed; restoring ${previous_image}..."
    BOT_IMAGE="${previous_image}" docker compose \
      --project-name youtube-discord-bot \
      --file "${COMPOSE_FILE}" \
      up -d --no-build --remove-orphans || true
  fi
  exit 1
fi

ready=0
for ((elapsed = 0; elapsed < READY_TIMEOUT_SECONDS; elapsed++)); do
  if ! docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
    break
  fi

  running="$(docker inspect --format '{{.State.Running}}' "${CONTAINER_NAME}")"
  if [ "${running}" != "true" ]; then
    break
  fi

  if docker logs "${CONTAINER_NAME}" 2>&1 | grep -Fq "${READY_LOG_TEXT}"; then
    ready=1
    break
  fi

  sleep 1
done

if [ "${ready}" -ne 1 ]; then
  echo "ERROR: New container did not become ready. Recent logs:"
  docker logs --tail 100 "${CONTAINER_NAME}" 2>&1 || true

  if [ -n "${previous_image}" ] && docker image inspect "${previous_image}" >/dev/null 2>&1; then
    echo "Rolling back to ${previous_image}..."
    BOT_IMAGE="${previous_image}" docker compose \
      --project-name youtube-discord-bot \
      --file "${COMPOSE_FILE}" \
      up -d --no-build --remove-orphans
  fi

  exit 1
fi

echo "Deployment completed: ${target_commit}"
