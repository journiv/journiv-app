#!/bin/sh
set -e

# /opt/venv survives volume mount .:/app; use venv Python for -m (shebangs in bin/ point to system python3.12)
PYTHON=/opt/venv/bin/python
echo "Ensuring data directories exist..."
mkdir -p /data/media /data/logs

if [ "${SERVICE_ROLE}" = "celery-worker" ]; then
  echo "Starting Celery worker..."
  exec "$PYTHON" -m celery -A app.core.celery_app worker --loglevel=info
elif [ "${SERVICE_ROLE}" = "celery-beat" ]; then
  echo "Starting Celery beat..."
  exec "$PYTHON" -m celery -A app.core.celery_app beat --loglevel=info --scheduler redbeat.RedBeatScheduler --pidfile=/tmp/celerybeat.pid
elif [ "${SERVICE_ROLE}" = "admin-cli" ]; then
  if [ $# -eq 0 ]; then
    echo "Starting admin-cli in idle mode (sleep infinity)..."
    exec sleep infinity
  fi
  # If arguments provided, they will be handled by the custom command block below
fi

# For app role or custom commands, we typically want migrations and seeds
if [ "${SERVICE_ROLE:-app}" = "app" ] || [ $# -gt 0 ]; then
  echo "Running database migrations in entrypoint script..."
  "$PYTHON" -c "from alembic.config import main; main(['upgrade', 'head'])"

  echo "Seeding initial data in entrypoint script..."
  SKIP_DATA_SEEDING=false "$PYTHON" -c "from app.core.database import seed_initial_data; seed_initial_data()"
fi

# If a custom command was passed (e.g. from docker-compose 'command' or 'docker run'), execute it
if [ $# -gt 0 ]; then
  echo "Executing custom command: $*"
  exec "$@"
fi

# Default behavior: Start Gunicorn if role is 'app'
if [ "${SERVICE_ROLE:-app}" = "app" ]; then
  RELOAD_FLAG=""
  if [ "${ENVIRONMENT}" = "development" ]; then
    echo "Starting Gunicorn in development mode with hot reload..."
    RELOAD_FLAG="--reload"
  else
    echo "Starting Gunicorn..."
  fi

  exec "$PYTHON" -m gunicorn app.main:app \
    ${RELOAD_FLAG} \
    -w ${GUNICORN_WORKERS:-2} \
    -k uvicorn.workers.UvicornWorker \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout ${GUNICORN_TIMEOUT:-300} \
    --access-logfile - \
    -b 0.0.0.0:8000
else
  echo "Service role '${SERVICE_ROLE}' has no default command. Exiting."
  exit 1
fi
