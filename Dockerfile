# =========================
# Stage 1: React Builder
# =========================
FROM node:24-bookworm-slim AS react-builder

WORKDIR /frontend

# Keep dependency installation cacheable and use the committed lockfile.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# =========================
# Stage 2: Python Builder
# =========================
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  PATH=/root/.local/bin:$PATH

WORKDIR /app

# Install build dependencies (includes ffmpeg and HEIF support)
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libffi-dev \
  libpq-dev \
  libmagic1 \
  libmagic-dev \
  curl \
  ffmpeg \
  libheif-dev \
  libde265-dev \
  && rm -rf /var/lib/apt/lists/* \
  && echo "🔍 Checking FFmpeg license (builder stage)..." \
  && ffmpeg -version | grep -E "enable-gpl|enable-nonfree" && (echo "❌ GPL/nonfree FFmpeg detected!" && exit 1) || echo "✅ LGPL FFmpeg build verified."

# Use system Python so venv symlinks point to /usr/local/bin (survives COPY to runtime)
COPY uv.lock pyproject.toml ./
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/
ENV UV_SYSTEM_PYTHON=1
RUN uv sync --locked --no-editable --no-install-project

# =========================
# Stage 3: Runtime
# =========================
FROM python:3.12-slim-bookworm AS runtime

ARG REQUIRE_PLUS_FEATURES=false

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONPATH=/app \
  PATH=/opt/venv/bin:/root/.local/bin:$PATH \
  ENVIRONMENT=production \
  LOG_LEVEL=INFO \
  REACT_WEB_BUILD_PATH=/opt/journiv/react-web \
  LEGACY_WEB_BUILD_PATH=/opt/journiv/legacy-web

WORKDIR /app

# Install runtime dependencies and verify ffmpeg license
RUN apt-get update && apt-get install -y --no-install-recommends \
  libmagic1 \
  curl \
  ffmpeg \
  libffi8 \
  libpq5 \
  ca-certificates \
  libheif1 \
  libde265-0 \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libharfbuzz-subset0 \
  && rm -rf /var/lib/apt/lists/* \
  && echo "🔍 Checking FFmpeg license (runtime stage)..." \
  && ffmpeg -version | grep -E "enable-gpl|enable-nonfree" && (echo "❌ GPL/nonfree FFmpeg detected!" && exit 1) || echo "✅ LGPL FFmpeg build verified."

# Copy venv to /opt/venv (survives volume mount .:/app in dev); symlinks point to /usr/local/bin/python3.12
COPY --from=builder /app/.venv /opt/venv

# Copy app code and assets
COPY app/ app/

# Validate Plus module presence in release builds
RUN if [ "$REQUIRE_PLUS_FEATURES" = "true" ]; then \
      ls -lh /app/app/plus/plus_features.cpython-312-*.so; \
    fi

# Copy database migration files
COPY alembic/ alembic/
COPY alembic.ini .

# Copy scripts directory (seed data and entrypoint)
COPY scripts/prompts.json scripts/prompts.json
COPY scripts/docker-entrypoint.sh scripts/docker-entrypoint.sh
COPY journiv-admin journiv-admin

# Copy both compiled SPAs. React is built in this Dockerfile; Flutter remains
# the intentionally tracked release artifact produced by journiv-frontend's
# build_web.sh with --base-href /legacy/.
COPY --from=react-builder /frontend/dist/ /opt/journiv/react-web/
COPY web/ /opt/journiv/legacy-web/

# Copy license
COPY LICENSE.md .

RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
  && mkdir -p /data/media /data/logs \
  && chmod +x scripts/docker-entrypoint.sh \
  && chmod +x journiv-admin \
  && chmod -R a+rX /opt/venv \
  && chmod o+x /usr/local/bin/python3.12 /usr/local/bin/python3 \
  && chmod -R a+rwX /data \
  && chown -R appuser:appuser /app /data /opt/venv /opt/journiv

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD sh -c 'case "${SERVICE_ROLE:-${SERVICE_ROLE_HEALTHCHECK:-app}}" in \
  celery-worker) /opt/venv/bin/python -m celery -A app.core.celery_app inspect ping -d "celery@$(hostname)" --timeout=5 | grep -q "pong" ;; \
  celery-beat) test -f /tmp/celerybeat.pid && kill -0 "$(cat /tmp/celerybeat.pid)" ;; \
  admin-cli) exit 0 ;; \
  plus-service) curl -f http://localhost:${APP_PORT:-8000}/health ;; \
  *) curl -f http://localhost:8000/api/v1/health ;; \
  esac'

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
