# Contributing to Journiv

Thank you for your interest in contributing to Journiv! This guide will help you get started with contributing to the backend.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [API Documentation Standards](#api-documentation-standards)
- [Testing](#testing)
- [Database Migrations](#database-migrations)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Getting Help](#getting-help)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors:

- Be respectful and inclusive in all interactions
- Provide constructive feedback with empathy
- Help others learn and grow through collaboration
- Respect different viewpoints, experiences, and skill levels
- Focus on what is best for the project and community

## Getting Started

### Prerequisites

Before you begin, ensure you have:

- **Python 3.12+** and **uv** - For local development ([install uv](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker & Docker Compose** - For containerized development (recommended)
- **Git** - For version control
- **A code editor** - VS Code, PyCharm, or your preferred editor

### Quick Start

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/journiv-app.git
   cd journiv-app
   ```

2. **Choose your development approach**

   **Option A: Docker (Recommended)**
   ```bash
   # Start with SQLite (recommended for quick development)
   docker compose -f docker-compose.dev.sqlite.yml up -d

   # Or with PostgreSQL (for testing PostgreSQL-specific features)
   docker compose -f docker-compose.dev.yml up -d
   ```

   **Option B: Local Development**
   ```bash
   # Install dependencies
   uv sync --group dev

   # Set up environment
   cp .env.template .env
   # Edit .env with your settings

   # Run migrations
   uv run alembic upgrade head

   # Start development server
   uv run uvicorn app.main:app --reload
   ```

3. **Access the application**
   - Frontend: http://localhost:8000
   - Interactive API Docs: http://localhost:8000/docs
   - Alternative Docs: http://localhost:8000/redoc
   - Health Check: http://localhost:8000/api/v1/health

## Development Setup

### Environment Configuration

The application uses environment variables for configuration. A template is provided:

```bash
# Copy the template
cp .env.template .env

# Edit with your settings
nano .env
```

**Key environment variables for development:**
```bash
# Database (local development uses relative paths)
DATABASE_URL=sqlite:///./journiv.db

# Security (generate a secure key for production)
SECRET_KEY=dev-secret-key-change-this

# Application
DEBUG=true
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# Storage (local development uses relative paths)
MEDIA_ROOT=./media
LOG_DIR=./logs
```

**Note:** Docker deployments use absolute paths (`/data/journiv.db`, `/data/media`) which are automatically configured in the compose files.

### Database Options

**SQLite (Default)**
- Zero configuration required
- Perfect for development and single-user setups
- Database automatically created on first run

**PostgreSQL (Optional)**
- For multi-user production-like testing
- Requires PostgreSQL service running
- Use `docker-compose.dev.yml` for PostgreSQL development

## Project Structure

```
journiv-backend/
├── app/                          # Application code
│   ├── api/v1/                   # API routes
│   │   ├── api.py                # Route registration
│   │   └── endpoints/            # Endpoint handlers
│   ├── core/                     # Core functionality
│   │   ├── config.py             # Application settings
│   │   ├── database.py           # Database setup
│   │   ├── security.py           # Auth utilities
│   │   └── logging_config.py    # Logging setup
│   ├── middleware/               # Custom middleware
│   │   ├── request_logging.py
│   │   ├── csp_middleware.py
│   │   └── trusted_host.py
│   ├── models/                   # SQLModel database models
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── services/                 # Business logic layer
│   ├── web/                      # Flutter web app (PWA)
│   └── main.py                   # FastAPI application entry
├── alembic/                      # Database migrations
│   ├── versions/                 # Migration files
│   └── env.py                    # Alembic configuration
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── conftest.py               # Test fixtures
├── scripts/                      # Utility scripts
│   ├── docker-entrypoint.sh      # Container startup script
│   ├── fresh_migration.sh        # Regenerate migrations (uv)
│   ├── test.sh                   # Test runner (uv sync + uv run pytest)
│   ├── moods.json                # Seed data
│   └── prompts.json              # Seed data
├── pyproject.toml                # Project and dependencies (uv)
├── uv.lock                       # Locked dependencies
├── docker-compose.yml            # Production compose
├── docker-compose.dev.yml        # Development compose
├── docker-compose.dev.sqlite.yml # Development (SQLite)
├── docker-compose.sqlite.yml     # Production (SQLite)
├── Dockerfile                    # Container image
├── .env.template                 # Environment template
├── env.template                  # Environment template (alt)
├── alembic.ini                   # Alembic config
└── pytest.ini                    # Test configuration
```

### Architecture Overview

Journiv follows a **service layer architecture** with clear separation of concerns:

**Layer Responsibilities:**

1. **API Endpoints** (`app/api/v1/endpoints/`)
   - Handle HTTP requests and responses
   - Validate input via Pydantic schemas
   - Authentication and authorization
   - Thin wrappers that delegate to services

2. **Services** (`app/services/`)
   - Business logic implementation
   - Database operations via SQLModel
   - Data transformations
   - Core functionality

3. **Models** (`app/models/`)
   - SQLModel database models
   - Define table structure and relationships
   - Used for database operations

4. **Schemas** (`app/schemas/`)
   - Pydantic models for API validation
   - Request and response serialization
   - Separate from database models for flexibility

5. **Middleware** (`app/middleware/`)
   - Request/response interception
   - Security headers (CSP, HSTS)
   - Request logging
   - Trusted host validation

**Key Design Principle:** Keep endpoints thin. All business logic belongs in services, not in endpoint handlers.

## Development Workflow

### 1. Create a Feature Branch

Always create a new branch for your work:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Your Changes

When implementing your changes:

1. **Follow the architecture** - Keep business logic in services, not endpoints
2. **Add tests** - Write tests for new functionality
3. **Update documentation** - Keep API docs current
4. **Follow code style** - Use type hints and follow PEP 8

Refer to [API Documentation Standards](#api-documentation-standards) when adding new endpoints.

### 3. Run Tests

Always run tests before committing:

```bash
# Run all tests (syncs task deps and runs pytest with coverage)
./scripts/test.sh

# Or run pytest directly with uv
uv run pytest
uv run pytest -m unit
uv run pytest -m integration
uv run pytest --cov=app --cov-report=html
uv run pytest tests/unit/test_user_service.py -v
```

### 4. Database Changes

If you modify database models:

```bash
# 1. Update the model in app/models/
# 2. Create migration
uv run alembic revision --autogenerate -m "add user timezone field"

# 3. Review the generated migration in alembic/versions/
# 4. Apply migration
uv run alembic upgrade head

# 5. Test the migration works correctly
```

**Important:** Always review auto-generated migrations before applying them.

### 5. Commit Your Changes

Write clear, descriptive commit messages:

```bash
git add .
git commit -m "feat: add timezone support for users"
```

**Conventional commit format:**
```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring without behavior change
- `perf:` - Performance improvement
- `style:` - Code style/formatting (no logic change)
- `chore:` - Maintenance (dependencies, build, CI/CD)

**Examples:**
```bash
feat: add password reset functionality
fix: resolve JWT expiration edge case
docs: update API authentication guide
test: add integration tests for journal endpoints
refactor: extract tag validation to separate function
```


## API Documentation Standards

This section defines the documentation standards for all API endpoints in the Journiv backend. We use a balanced approach that provides essential information without overwhelming verbosity since the project is in active development and APIs continue to evolve.

---

### Standard Template

```python
@router.{method}(
    "/path",
    response_model=ResponseSchema,
    responses={
        400: {"description": "Brief description of client error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive / Permission denied"},
        404: {"description": "Resource not found"},
        500: {"description": "Server error description"},
    }
)
async def endpoint_name(
    dependencies: Annotated[Type, Depends(dependency)]
):
    """
    Brief one-line summary of what the endpoint does.

    Optional 1-2 sentence description providing key behavioral details
    or important security/business logic information.
    """
    # Implementation
```

**Key principle:** Error responses are documented in the `responses` parameter, NOT in docstrings. This ensures FastAPI's Swagger UI displays complete, accurate API documentation.

---

### Examples by Endpoint Type

#### **GET Endpoint (Simple)**
```python
@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
    }
)
async def get_user(
    user_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """Get user by ID."""
```

#### **GET Endpoint (List with Filters)**
```python
@router.get(
    "/entries",
    response_model=List[EntryResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied to journal"},
    }
)
async def list_entries(
    journal_id: Optional[str] = None,
    limit: int = 50,
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    List journal entries with optional filtering.

    Returns paginated entries ordered by creation date (newest first).
    """
```

#### **POST Endpoint (Create)**
```python
@router.post(
    "/journals",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid journal data"},
        401: {"description": "Not authenticated"},
        409: {"description": "Journal with same name already exists"},
    }
)
async def create_journal(
    journal_data: JournalCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Create a new journal."""
```

#### **PUT Endpoint (Update with Side Effects)**
```python
@router.put(
    "/me",
    response_model=UserResponse,
    responses={
        400: {"description": "Invalid data, incorrect password, or no fields to update"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def update_current_user(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Update current user profile.

    Password changes require current password verification and will revoke all active sessions.
    """
```

#### **DELETE Endpoint**
```python
@router.delete(
    "/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not entry owner"},
        404: {"description": "Entry not found"},
    }
)
async def delete_entry(
    entry_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Delete journal entry (soft delete)."""
```

---

### Error Response Standardization

Use consistent status codes across the API:

| Code | Usage | Example |
|------|-------|---------|
| **200** | Successful GET, PUT, DELETE (with body) | User retrieved |
| **201** | Successful POST (created) | Journal created |
| **204** | Successful DELETE (no body) | Entry deleted |
| **400** | Client error (validation, business logic) | Invalid password |
| **401** | Not authenticated | Missing/invalid token |
| **403** | Authenticated but forbidden | Not resource owner |
| **404** | Resource not found | Journal doesn't exist |
| **409** | Conflict (duplicate) | Email already registered |
| **422** | Unprocessable entity (Pydantic validation) | Auto-generated |
| **500** | Server error | Database connection failed |

---

### Tools & Automation

#### **FastAPI Auto-Documentation**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

#### **Type Hints as Documentation**
```python
# This is self-documenting:
async def create_entry(
    entry_data: EntryCreate,  # Schema documents structure
    current_user: Annotated[User, Depends(get_current_user)],  # Auth requirement clear
    session: Annotated[Session, Depends(get_session)]  # DB dependency explicit
) -> EntryResponse:  # Return type documented
```

## Testing

### Test Structure

Tests are organized by type:

```
tests/
├── unit/                     # Unit tests (fast, isolated)
│   ├── test_user_service.py
│   ├── test_journal_service.py
│   └── ...
├── integration/              # Integration tests (API endpoints)
│   ├── test_auth_endpoints.py
│   ├── test_journal_endpoints.py
│   └── ...
└── conftest.py              # Shared fixtures and configuration
```

### Running Tests

**Using the test script (recommended):**
```bash
./scripts/test.sh                  # All tests with coverage
./scripts/test.sh --markers unit   # Unit tests only
./scripts/test.sh --markers integration
./scripts/test.sh --parallel --fail-fast
./scripts/test.sh --no-coverage -v
```

**Using uv run pytest directly:**
```bash
uv run pytest
uv run pytest -m unit
uv run pytest -m integration
uv run pytest tests/unit/test_user_service.py
uv run pytest --cov=app --cov-report=html
uv run pytest -n auto -v -x
```

**Using Docker:**
```bash
docker compose -f docker-compose.dev.sqlite.yml run app pytest
docker compose -f docker-compose.dev.sqlite.yml run app pytest --cov=app
```

### Writing Tests

**Unit Tests** - Test individual functions/services:
```python
def test_create_user_success(session: Session):
    user_data = UserCreate(email="test@example.com", password="password123")
    user = user_service.create_user(session, user_data)
    assert user.email == "test@example.com"
    assert user.id is not None
```

**Integration Tests** - Test complete API flows:
```python
def test_create_journal_endpoint(client: TestClient, auth_headers: dict):
    journal_data = {"name": "My Journal", "description": "Test journal"}
    response = client.post("/api/v1/journals/", json=journal_data, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["name"] == "My Journal"
```

### Test Coverage

**Target:** Maintain at least 70% test coverage for all new code.

Coverage reports are generated in:
- **Terminal**: Summary statistics
- **HTML**: `htmlcov/index.html` (detailed file-by-file report)
- **XML**: `coverage.xml` (for CI/CD integration)

**Best practices:**
- Write tests alongside new features
- Cover both success and error paths
- Test edge cases and boundary conditions
- Mock external dependencies in unit tests

## Database Migrations

### Creating Migrations

When you modify database models:

1. **Update the model** in `app/models/`
2. **Create migration**
   ```bash
   uv run alembic revision --autogenerate -m "description of changes"
   ```
3. **Review the generated migration** in `alembic/versions/`
4. **Apply migration** (local: `uv run alembic upgrade head`, or via Docker):
   ```bash
   ./scripts/migrate.sh
   ```

### Migration Best Practices

- **Always review** generated migrations before applying
- **Test migrations** on a copy of production data
- **Use descriptive names** for migration messages
- **Don't edit** existing migration files (create new ones instead)

### Fresh Migration (Development Only)

When you need to regenerate migrations from scratch during development:

```bash
./scripts/fresh_migration.sh
```

This script runs `uv sync` then:
1. Deletes the SQLite database file
2. Removes all existing migration files
3. Generates a fresh initial migration (`uv run alembic revision --autogenerate`)
4. Fixes any import issues in the migration (`uv run python scripts/fix_migration_imports.py`)

⚠️ **Warning**: This deletes your database and all migrations. **Only use in development**, never in production!

## Code Style

### Python Style

- Follow **PEP 8** guidelines
- Use **type hints** for all function parameters and return values
- Use **SQLModel** for database models
- Use **Pydantic** for request/response schemas

### Import Organization

```python
# Standard library imports
import os
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

# Local imports
from app.core.database import get_session
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import user_service
```

## Pull Request Process

### Before Submitting

Ensure your pull request meets these requirements:

1. **All tests pass**
   ```bash
   ./scripts/test.sh
   # or: uv run pytest && uv run pytest --cov=app
   ```

2. **Code follows style guidelines**
   - Use type hints for all functions
   - Follow PEP 8 conventions
   - Keep functions focused and small
   - Add docstrings to public functions

3. **Documentation is updated**
   - API endpoint docstrings
   - README if adding features
   - Code comments for complex logic

4. **Manual testing completed**
   - Test happy path
   - Test error cases
   - Verify in browser/API client if applicable

5. **Migrations are included** (if database changes)
   ```bash
   # Ensure migrations are committed
   git status alembic/versions/
   ```

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
```

### Review Process

Your pull request will go through these stages:

1. **Automated checks** - CI/CD tests must pass
2. **Code review** - Maintainers review code quality and design
3. **Testing verification** - Ensure adequate test coverage
4. **Documentation review** - Verify docs are up to date
5. **Approval and merge** - Approved PRs are merged to main branch

**Review tips:**
- Respond to feedback promptly
- Be open to suggestions and improvements
- Keep PRs focused on a single feature/fix
- Update your PR based on review comments

## Getting Help

Need assistance or have questions?

**Development Questions:**
- **GitHub Discussions**: Ask questions and get help from the community
- **GitHub Issues**: Report bugs or request features
- **Documentation**: Check [README.md](README.md) for setup and usage

**Technical Resources:**
- **API Docs**: http://localhost:8000/docs (when running locally)
- **Project Structure**: See [Project Structure](#project-structure) section
- **Architecture Guide**: See [Architecture Overview](#architecture-overview)

**Community:**
- **Discord**: Join our [community server](https://discord.gg/CuEJ8qft46)
- **Email**: journiv@protonmail.com

## License

By contributing to Journiv, you agree that your contributions will be licensed under the same license as the project. See the [LICENSE](LICENSE) file for details.

---

**Thank you for contributing to Journiv!**

Your contributions help make Journiv better for everyone. We appreciate your time and effort in improving this project.
