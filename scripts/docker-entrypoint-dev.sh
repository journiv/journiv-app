#!/bin/sh
set -e

echo "Ensuring data directories exist..."
mkdir -p /data/media /data/logs

echo "Running database migrations..."
alembic upgrade head

echo "Seeding initial data (moods, prompts)..."
SKIP_DATA_SEEDING=false python -c "from app.core.database import seed_initial_data; seed_initial_data()"

echo "Starting Uvicorn in development mode with hot reload..."
# Development uses single Uvicorn process with --reload for hot reloading
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
