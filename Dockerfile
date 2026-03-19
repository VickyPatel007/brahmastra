# ─────────────────────────────────────────────────────────────────────────────
# Brahmastra — Multi-Stage Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Build:  docker build -t brahmastra .
# Run:    docker run -p 8000:8000 --env-file .env brahmastra
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Vivek Patel <viveksherathiya12@gmail.com>"
LABEL description="Brahmastra — Self-Healing Infrastructure Monitoring System"
LABEL version="2.0.0"

WORKDIR /app

# Install runtime-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash brahmastra

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/ ./backend/
COPY dashboard/ ./dashboard/

# Create directories for runtime data
RUN mkdir -p /app/data /app/logs && \
    chown -R brahmastra:brahmastra /app

# Switch to non-root user
USER brahmastra

# Environment defaults (override via --env-file or -e)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BAN_STATE_FILE=/app/data/bans.json \
    LOG_LEVEL=info

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Brahmastra API
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
