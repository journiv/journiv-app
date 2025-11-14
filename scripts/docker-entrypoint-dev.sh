#!/bin/sh
set -e

echo "Ensuring data directories exist..."
mkdir -p /data/media /data/logs

echo "Running database migrations in entrypoint script..."
alembic upgrade head

echo "Seeding initial data in entrypoint script..."
SKIP_DATA_SEEDING=false python -c "from app.core.database import seed_initial_data; seed_initial_data()"

echo "Starting Gunicorn in development mode with hot reload..."
exec gunicorn app.main:app \
    -w ${GUNICORN_WORKERS:-2} \
    -k uvicorn.workers.UvicornWorker \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    -b 0.0.0.0:8000
