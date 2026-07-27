FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/.cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 1000 bot

COPY --chown=bot:bot . .
RUN python -m compileall -q /app \
    && find /app -type d -name __pycache__ -prune -exec rm -rf {} + \
    && mkdir -p /app/downloads/tmp \
    && chown -R bot:bot /app/downloads

USER bot

CMD ["python", "main.py"]
