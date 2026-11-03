FROM denoland/deno:bin-2.9.4 AS deno

FROM node:24-slim AS frontend
WORKDIR /frontend
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    XDG_CACHE_HOME=/tmp/.cache

COPY --from=deno /deno /usr/local/bin/deno

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libmysofa1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 1000 bot

COPY --chown=bot:bot . .
COPY --from=frontend --chown=bot:bot /frontend/dist /app/web/dist
RUN python -m compileall -q /app \
    && find /app -type d -name __pycache__ -prune -exec rm -rf {} + \
    && mkdir -p /app/downloads/tmp /app/data \
    && chown -R bot:bot /app/downloads /app/data

USER bot

CMD ["python", "main.py"]
