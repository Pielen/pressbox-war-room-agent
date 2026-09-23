# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install system certificates for HTTPS calls to MLB (statsapi.mlb.com) and NHL (api-web.nhle.com)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY pressbox_war_room/ ./pressbox_war_room/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[gcp]"

EXPOSE 8080

# Launch Google ADK FastAPI Server (`adk api_server`) for Cloud Run / Agent Engine
CMD ["sh", "-c", "adk api_server --host 0.0.0.0 --port ${PORT:-8080} ."]
