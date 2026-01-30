#!/usr/bin/env bash

# Regenerates the initial Alembic migration for a clean SQLite database.
# All existing migration files and the SQLite database file are removed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "Fresh Initial Migration Generator (SQLite)"
echo "=========================================="
echo ""
echo "WARNING: This will delete your local SQLite database file and migrations."
echo "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

# Capture DATABASE_URL passed via environment so it can override .env
CLI_DATABASE_URL="${DATABASE_URL:-}"

# Load environment variables if .env exists so DATABASE_URL is available
if [ -f ".env" ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

# Allow CLI-provided DATABASE_URL to take precedence
if [[ -n "${CLI_DATABASE_URL}" ]]; then
  DATABASE_URL="${CLI_DATABASE_URL}"
fi

DATABASE_URL=${DATABASE_URL:-"sqlite:///./journiv.db"}

uv sync --locked

if [[ "${DATABASE_URL}" != sqlite://* ]]; then
  echo "ERROR: This script currently only supports SQLite DATABASE_URL values."
  echo "Current DATABASE_URL='${DATABASE_URL}'"
  exit 1
fi

# Resolve the SQLite file path using Python for reliability
DB_PATH="$(uv run python - "${DATABASE_URL}" "${PROJECT_ROOT}" <<'PY'
import os
import sys
from sqlalchemy.engine import make_url

raw_url = sys.argv[1]
project_root = sys.argv[2]

url = make_url(raw_url)

if url.drivername != "sqlite":
    sys.exit(0)

database = url.database or ""

if database in ("", ":memory:"):
    print(":memory:")
else:
    if not os.path.isabs(database):
        database = os.path.join(project_root, database)
    print(os.path.abspath(database))
PY
)"

if [[ -z "${DB_PATH}" ]]; then
  echo "ERROR: Unable to resolve SQLite path from DATABASE_URL='${DATABASE_URL}'."
  exit 1
fi

if [[ "${DB_PATH}" == ":memory:" ]]; then
  echo ""
  echo "ℹ︎ DATABASE_URL points to an in-memory SQLite database; skipping file deletion."
else
  echo ""
  echo "Step 1: Removing SQLite database file..."
  if [ -f "${DB_PATH}" ]; then
    rm -f "${DB_PATH}"
    echo "✓ Removed ${DB_PATH}"
  else
    echo "ℹ︎ No database file found at ${DB_PATH}"
  fi
fi

# Step 2: Clean existing migration files
echo ""
echo "Step 2: Cleaning up old migration files..."
rm -f alembic/versions/*.py
mkdir -p alembic/versions
touch alembic/versions/.gitkeep
echo "✓ Old migrations removed"

# Step 3: Generate fresh migration
echo ""
echo "Step 3: Generating fresh initial migration..."
DATABASE_URL="${DATABASE_URL}" uv run alembic revision --autogenerate -m "initial schema"
echo "✓ Initial migration generated"

# Step 3.5: Fix migration imports
echo ""
echo "Step 3.5: Fixing migration imports..."
uv run python scripts/fix_migration_imports.py
echo "✓ Migration imports fixed"

# Step 4: Show summary
MIGRATION_FILE=$(ls -t alembic/versions/*.py 2>/dev/null | head -1)
if [ -n "${MIGRATION_FILE}" ]; then
  echo ""
  echo "Generated migration: ${MIGRATION_FILE}"
  TABLES=$(grep -c "op.create_table" "${MIGRATION_FILE}" 2>/dev/null || echo "0")
  INDEXES=$(grep -c "op.create_index" "${MIGRATION_FILE}" 2>/dev/null || echo "0")
  echo "  - Tables to create: ${TABLES}"
  echo "  - Indexes to create: ${INDEXES}"
fi

echo ""
echo "=========================================="
echo "✓ Fresh migration generated successfully!"
echo "=========================================="
echo "Next steps:"
echo "1. Inspect the migration: cat ${MIGRATION_FILE}"
echo "2. Apply it: DATABASE_URL=${DATABASE_URL} uv run alembic upgrade head"
echo "3. Run tests to verify schema"
