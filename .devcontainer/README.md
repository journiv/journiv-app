# Journiv Dev Container Setup

This directory contains VS Code Dev Container configurations for the Journiv application.

## Available Configurations

### 1. SQLite Development (Default)
**File:** `devcontainer.json`

The default development environment using SQLite as the database. This is the simplest setup and recommended for most development work.

**Features:**
- Uses SQLite database at `/data/journiv.db`
- Hot reload enabled
- All Python development tools pre-configured
- Database viewer extension included

**To use:**
1. Open the project in VS Code
2. Press `F1` and select "Dev Containers: Reopen in Container"
3. Wait for the container to build and start
4. Start developing!

### 2. PostgreSQL Development
**File:** `devcontainer.postgres.json`

Advanced development environment using PostgreSQL as the database. Use this when you need to test PostgreSQL-specific features or replicate production-like conditions.

**Features:**
- PostgreSQL 15 database
- Separate database container
- PostgreSQL connection pre-configured in SQLTools
- All Python development tools

**To use:**
1. Open the project in VS Code
2. Press `F1` and select "Dev Containers: Open Container Configuration File"
3. Select `devcontainer.postgres.json`
4. Press `F1` and select "Dev Containers: Reopen in Container"
5. Wait for both containers (app and PostgreSQL) to start

## What's Included

### VS Code Extensions
- **Python Development:** Python, Pylance, debugpy
- **Code Quality:** Black formatter, isort, flake8
- **Database Tools:** SQLTools with SQLite and PostgreSQL drivers
- **Docker Support:** Docker extension for container management
- **API Testing:** REST Client for testing API endpoints
- **Git Integration:** GitLens for enhanced Git features
- **Productivity:** Error Lens, Better Comments, Code Spell Checker

### Pre-configured Settings
- **Formatting:** Black with 88 character line length
- **Import Sorting:** isort with Black profile
- **Linting:** flake8 enabled
- **Testing:** pytest configured
- **Auto-format on save:** Enabled for Python files
- **Database connections:** Pre-configured based on environment

## Development Workflow

### Starting the Application
The application starts automatically when the container starts with hot reload enabled:
```bash
# Already running - just save your files and they'll auto-reload
```

### Running Tests
```bash
pytest
```

### Database Migrations
```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Accessing the API
- API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/health

### Database Access

#### SQLite
Use the SQLTools extension:
1. Click the database icon in the left sidebar
2. Select "Journiv SQLite (Dev)"
3. Browse tables and run queries

Or use the command line:
```bash
sqlite3 /data/journiv.db
```

#### PostgreSQL
Use the SQLTools extension:
1. Click the database icon in the left sidebar
2. Select "Journiv PostgreSQL (Dev)"
3. Browse tables and run queries

Or use psql:
```bash
# From within the container
psql -h postgres -U journiv -d journiv_dev
```

## Environment Variables

Environment variables are set in `docker-compose.dev.yml`. Common ones:

- `DEBUG=true` - Enable debug mode
- `LOG_LEVEL=INFO` - Set logging level
- `DATABASE_URL` - Database connection string (SQLite)
- `POSTGRES_*` - PostgreSQL connection details (PostgreSQL mode)
- `ENABLE_CORS=true` - CORS enabled for local frontend development

## Port Forwarding

The following ports are automatically forwarded:
- **8000** - Journiv API (both configurations)
- **5432** - PostgreSQL (PostgreSQL configuration only)

## Troubleshooting

### Container won't start
```bash
# Rebuild the container
docker-compose -f docker-compose.dev.yml build --no-cache
```

### Database permissions issues
```bash
# Fix data directory permissions
sudo chown -R 1000:1000 ./data
```

### Need to reset the database
```bash
# SQLite - delete the database file
rm -f ./data/journiv.db

# PostgreSQL - drop and recreate
docker-compose -f docker-compose.dev.yml --profile postgres down -v
docker-compose -f docker-compose.dev.yml --profile postgres up -d
```

### Python packages not found
```bash
# Reinstall development dependencies
pip install -r requirements/dev.txt
```

## Switching Between Configurations

To switch from SQLite to PostgreSQL (or vice versa):

1. Press `F1` in VS Code
2. Select "Dev Containers: Rebuild and Reopen in Container"
3. When prompted, select the configuration you want to use

Alternatively:
1. Close the current container
2. Edit `.devcontainer/devcontainer.json` to point to the config you want
3. Reopen in container

## Additional Resources

- [Journiv Documentation](../README.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
- [VS Code Dev Containers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
