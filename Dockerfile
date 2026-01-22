# =========================
# Stage 1: Builder
# =========================
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  PATH=/root/.local/bin:$PATH

WORKDIR /app

# Install build dependencies (includes ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libffi-dev \
  libpq-dev \
  libmagic1 \
  libmagic-dev \
  curl \
  ffmpeg \
  && rm -rf /var/lib/apt/lists/* \
  && echo "🔍 Checking FFmpeg license (builder stage)..." \
  && ffmpeg -version | grep -E "enable-gpl|enable-nonfree" && (echo "❌ GPL/nonfree FFmpeg detected!" && exit 1) || echo "✅ LGPL FFmpeg build verified."

# Copy requirements and install Python deps
COPY requirements/ requirements/
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements/prod.txt

# =========================
# Stage 2: Runtime
# =========================
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  PATH=/root/.local/bin:$PATH \
  ENVIRONMENT=production \
  LOG_LEVEL=INFO

WORKDIR /app

# Install runtime dependencies and verify ffmpeg license
RUN apt-get update && apt-get install -y --no-install-recommends \
  libmagic1 \
  curl \
  ffmpeg \
  libffi8 \
  libpq5 \
  ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && echo "🔍 Checking FFmpeg license (runtime stage)..." \
  && ffmpeg -version | grep -E "enable-gpl|enable-nonfree" && (echo "❌ GPL/nonfree FFmpeg detected!" && exit 1) || echo "✅ LGPL FFmpeg build verified."

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/
COPY --from=builder /usr/local/bin/celery /usr/local/bin/
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/

# Copy app code and assets
COPY app/ app/

# Copy database migration files
COPY alembic/ alembic/
COPY alembic.ini .

# Copy scripts directory (seed data and entrypoint)
COPY scripts/moods.json scripts/moods.json
COPY scripts/prompts.json scripts/prompts.json
COPY scripts/docker-entrypoint.sh scripts/docker-entrypoint.sh
COPY scripts/migrate_media_storage.py scripts/migrate_media_storage.py

# Copy prebuilt Flutter web app
COPY web/ web/

# Copy license
COPY LICENSE.md .

# Create non-root user and set up data directories
RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
  && mkdir -p /data/media /data/logs \
  && chmod +x scripts/docker-entrypoint.sh \
  # Fix permissions in case some directories gets copied as 700
  && chmod -R u+rwX,g+rX /app \
  && chmod -R a+rwX /data \
  && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD sh -c 'case "${SERVICE_ROLE:-app}" in \
  celery-worker) celery -A app.core.celery_app inspect ping -d "celery@$(hostname)" --timeout=5 | grep -q "pong" ;; \
  celery-beat) test -f /tmp/celerybeat.pid && kill -0 "$(cat /tmp/celerybeat.pid)" ;; \
  *) curl -f http://localhost:8000/api/v1/health ;; \
  esac'

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
