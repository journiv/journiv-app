# Journiv Upgrade Testing System

This directory contains end-to-end upgrade tests that validate data preservation when upgrading Journiv from one version to another.

## Overview

The upgrade test suite ensures that:
- ✅ User data is preserved across version upgrades
- ✅ Database migrations execute successfully
- ✅ All existing features continue to work
- ✅ No data loss occurs during the upgrade process

## Architecture

The upgrade testing workflow consists of three phases:

### Phase 1: Seed Old Version
1. Start the OLD version (e.g., `0.1.0-beta.6` from Docker Hub)
2. Create realistic test data via API calls
3. Verify data was created successfully

### Phase 2: Upgrade
1. Stop the old version (preserving data volumes)
2. Build the NEW version (current codebase)
3. Start the new version with the same data volumes
4. Wait for application readiness

### Phase 3: Verify New Version
1. Login with existing credentials
2. Verify all data is still accessible
3. Check data integrity and counts
4. Validate new features work correctly

## Files

- **`helpers.py`** - Shared HTTP/API utilities for making requests to Journiv
- **`seed_old_data.py`** - Creates test data in the OLD version
- **`verify_after_upgrade.py`** - Validates data after upgrading to NEW version
- **`README.md`** - This documentation

## Test Data Created

The seeding phase creates:
- 1 test user with credentials
- 2 journals (Work Journal, Personal Journal)
- 4+ journal entries (with different dates)
- 4+ tags (work, planning, personal, gratitude)
- 3+ mood logs associated with entries
- 1 text media file upload
- User settings

All data IDs and relationships are preserved during upgrade.

## Running Tests Locally

### Prerequisites
```bash
# Install test dependencies
pip install -r requirements/test.txt
```

### Manual Test Run

#### Step 1: Start OLD version
```bash
# Using SQLite
docker compose -f docker-compose.sqlite.yml up -d

# Or using PostgreSQL
docker compose -f docker-compose.postgres.yml up -d
```

#### Step 2: Seed data into OLD version
```bash
# Wait for application to be ready
curl http://localhost:8000/health

# Run seeding script
python -m pytest tests/upgrade/seed_old_data.py -v
```

#### Step 3: Upgrade to NEW version
```bash
# Stop old version (preserve volumes)
docker compose down

# Build new version
docker build -t journiv-backend:latest .

# Start new version
docker compose up -d
```

#### Step 4: Verify upgrade
```bash
# Wait for application to be ready
curl http://localhost:8000/health

# Run verification tests
python -m pytest tests/upgrade/verify_after_upgrade.py -v
```

#### Cleanup
```bash
docker compose down -v
```

## GitHub Actions Workflow

The upgrade tests run automatically in CI via `.github/workflows/upgrade-tests.yml`:

### Triggers
- Push to `main` branch
- Pull requests affecting backend code
- Manual workflow dispatch

### Matrix Testing
Tests run against both databases:
- SQLite
- PostgreSQL

### Version Configuration
```yaml
OLD_VERSION: "0.1.0-beta.6"  # Previous stable release
NEW_VERSION: "ci-latest"      # Built from current code
```

### Workflow Steps
1. ✅ Pull OLD version from Docker Hub
2. ✅ Start OLD version with isolated project name
3. ✅ Seed realistic test data
4. ✅ Stop OLD version (preserve volumes)
5. ✅ Build NEW version
6. ✅ Start NEW version (reuse volumes)
7. ✅ Verify data integrity
8. ✅ Cleanup

## Test Credentials

The upgrade tests use consistent credentials:

```python
TEST_EMAIL = "upgrade-test@journiv.com"
TEST_PASSWORD = "UpgradeTest123!"
```

These credentials are used in both seeding and verification phases.

## Volume Preservation

The workflow uses Docker Compose project isolation to prevent volume conflicts:

```bash
COMPOSE_PROJECT_NAME=ci_${GITHUB_RUN_ID}_${DATABASE}
```

This ensures:
- ✅ Each CI run gets unique volumes
- ✅ Parallel matrix jobs don't interfere
- ✅ Volumes are properly preserved between OLD→NEW transition


## Troubleshooting

### Test Fails: "Health check failed"

The application may take longer to start. Increase timeout:

```python
wait_for_ready(max_attempts=60, delay=2)  # Wait up to 2 minutes
```

### Test Fails: "Data loss detected"

Check:
1. ✅ Volumes were preserved (no `-v` flag on `docker compose down`)
2. ✅ Database migrations completed successfully
3. ✅ Logs for migration errors: `docker compose logs`

### Test Fails: "Login failed"

Check:
1. ✅ Old version successfully seeded data
2. ✅ Password hashing is compatible across versions
3. ✅ User table schema hasn't changed incompatibly

### Docker Volume Not Found

Ensure project name consistency:

```bash
# Use same project name for both old and new
docker compose -p my_project down
docker compose -p my_project up -d
```
