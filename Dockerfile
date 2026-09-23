# syntax=docker/dockerfile:1
# Stage 1: Builder image for dependency compilation and wheel caching
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements.txt pyproject.toml README.md ./
COPY pressbox_war_room/ ./pressbox_war_room/

RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt .

# Stage 2: Hardened non-root production runtime image
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    WAR_ROOM_SQLITE_PATH=/var/lib/pressbox/war_room.db

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home --shell /sbin/nologin appuser \
    && mkdir -p /var/lib/pressbox /app \
    && chown -R appuser:appgroup /var/lib/pressbox /app

WORKDIR /app

COPY --from=builder /build/wheels /wheels
COPY pyproject.toml README.md ./
COPY pressbox_war_room/ ./pressbox_war_room/

RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8080}/list-apps || exit 1

CMD ["sh", "-c", "adk api_server --host 0.0.0.0 --port ${PORT:-8080} ."]
