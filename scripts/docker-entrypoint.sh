#!/bin/sh
set -e

echo "Ensuring data directories exist..."
mkdir -p /data/media /data/logs

if [ "${SERVICE_ROLE:-app}" = "celery-worker" ]; then
  echo "Starting Celery worker..."
  exec celery -A app.core.celery_app worker --loglevel=info
elif [ "${SERVICE_ROLE:-app}" = "celery-beat" ]; then
  echo "Starting Celery beat..."
  exec celery -A app.core.celery_app beat --loglevel=info --scheduler redbeat.RedBeatScheduler --pidfile=/tmp/celerybeat.pid
fi

echo "Running database migrations in entrypoint script..."
alembic upgrade head

echo "Seeding initial data in entrypoint script..."
SKIP_DATA_SEEDING=false python -c "from app.core.database import seed_initial_data; seed_initial_data()"

echo "Starting Gunicorn..."
# Production uses 2 workers for optimal resource usage
# Increase -w flag if you need higher concurrency
exec gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --worker-connections 1000 --max-requests 1000 --max-requests-jitter 100 --timeout 120 --access-logfile - -b 0.0.0.0:8000
