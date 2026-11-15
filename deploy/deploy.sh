#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${YOUTUBE_BOT_REPO_DIR:-/youtube-bot}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
CONTAINER_NAME="youtube-bot"
READY_LOG_TEXT="としてログインしました"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"
DEPLOY_UID="${DEPLOY_UID:-1000}"
DEPLOY_GID="${DEPLOY_GID:-1000}"
LOCK_FILE="${REPO_DIR}/deploy/.deploy.lock"
WEB_ASSETS_VOLUME="${WEB_ASSETS_VOLUME:-youtube-discord-bot_youtube-bot-web}"

publish_web() {
  docker run --rm --network none --user 0 \
    --mount "type=volume,source=${WEB_ASSETS_VOLUME},target=/published" \
    --entrypoint python "$1" /app/deploy/publish_web.py
}

record_image() {
  if grep -q '^BOT_IMAGE=' .env; then
    sed -i "s|^BOT_IMAGE=.*$|BOT_IMAGE=${candidate_image}|" .env
  else
    printf '\nBOT_IMAGE=%s\n' "${candidate_image}" >> .env
  fi
  chmod 600 .env
}

repair_ownership() {
  chown -R "${DEPLOY_UID}:${DEPLOY_GID}" "${REPO_DIR}" 2>/dev/null || true
}

finish() {
  status=$?
  trap - EXIT
  set +e

  if [ "${status}" -ne 0 ] && [ "${restore_checkout:-0}" = 1 ] && [ -n "${previous_commit:-}" ] && [ -d "${REPO_DIR}/.git" ]; then
    echo "Restoring checkout to ${previous_commit}..."
    git -C "${REPO_DIR}" reset --hard "${previous_commit}"
  fi

  if [ "${status}" -ne 0 ] && [ "${deployment_started:-0}" = 1 ] && [ -n "${previous_image:-}" ]; then
    echo "Restoring the previous running image and frontend..."
    BOT_IMAGE="${previous_image}" docker compose --project-name youtube-discord-bot --file "${COMPOSE_FILE}" up -d --no-build --remove-orphans
    if grep -Eq '^WEB_ENABLED=true' .env; then
      publish_web "${previous_frontend_image:-${previous_image}}" || true
    fi
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
previous_frontend_image="$(sed -n 's/^BOT_IMAGE=//p' .env | tail -1)"

echo "Fetching origin/main..."
git fetch --prune origin main
target_commit="$(git rev-parse origin/main)"

# 初回GUI統合前のmainで、稼働中のWebを古いBotへ戻さない。
if grep -Eq '^WEB_ENABLED=true' .env; then
  if ! git cat-file -e "${target_commit}:web/package-lock.json" 2>/dev/null; then
    echo "origin/main does not contain the Web GUI yet; keeping the current release."
    exit 0
  fi
fi

if [ "${previous_commit}" = "${target_commit}" ]; then
  echo "origin/main is already deployed (${target_commit})."
  exit 0
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: Tracked server changes must be preserved and reconciled before deployment."
  exit 1
fi

# 書き換える前のクリーンなcheckoutを記録する。
restore_checkout=1
frontend_only=1
while IFS= read -r changed; do
  case "${changed}" in
    web/*|docs/*|README.md|.github/*) ;;
    *) frontend_only=0 ;;
  esac
done < <(git diff --name-only "${previous_commit}" "${target_commit}")

echo "Updating checkout: ${previous_commit} -> ${target_commit}"
git reset --hard "${target_commit}"

candidate_image="youtube-discord-bot:${target_commit}"
echo "Building ${candidate_image}..."
docker build --pull --tag "${candidate_image}" "${REPO_DIR}"
docker run --rm --network none --env DISCORD_TOKEN=deployment-test \
  --entrypoint python "${candidate_image}" -m unittest discover -s tests -q

if [ "${frontend_only}" = 1 ] && grep -Eq '^WEB_ENABLED=true' .env; then
  publish_web "${candidate_image}"
  record_image
  echo "Frontend published without restarting Discord playback: ${target_commit}"
  exit 0
fi

echo "Waiting for voice playback and downloads to finish..."
idle_deadline=$((SECONDS + ${IDLE_WAIT_SECONDS:-21600}))
while docker inspect --format '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null | grep -q true; do
  if docker exec -i "${CONTAINER_NAME}" python < "${REPO_DIR}/deploy/check_idle.py"; then
    break
  fi
  if [ "${SECONDS}" -ge "${idle_deadline}" ]; then
    echo "ERROR: Bot remained active; keeping the current container."
    exit 1
  fi
  sleep 15
done

echo "Starting ${CONTAINER_NAME}..."
deployment_started=1
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
    if docker exec "${CONTAINER_NAME}" python -c \
      'import os,urllib.request; assert os.getenv("WEB_ENABLED", "false").lower() != "true" or urllib.request.urlopen("http://127.0.0.1:8080/healthz",timeout=3).status == 200' >/dev/null 2>&1; then
      ready=1
      break
    fi
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

if grep -Eq '^WEB_ENABLED=true' .env; then
  publish_web "${candidate_image}"
fi
record_image
echo "Deployment completed: ${target_commit}"
