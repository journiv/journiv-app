"""
Unit tests for app.core.config module, specifically testing DB_DRIVER validation.
"""
import pytest
from pydantic import ValidationError

from app.core.config import Settings, DEFAULT_SQLITE_URL


class TestDBDriverValidation:
    """Test DB_DRIVER field validation and requirements."""

    def test_db_driver_defaults_to_sqlite(self):
        """Test that DB_DRIVER defaults to 'sqlite' when not specified."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            database_url=DEFAULT_SQLITE_URL,
        )
        assert settings.db_driver == "sqlite"

    def test_db_driver_accepts_sqlite(self):
        """Test that DB_DRIVER accepts 'sqlite' value."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="sqlite",
            database_url=DEFAULT_SQLITE_URL,
        )
        assert settings.db_driver == "sqlite"

    def test_db_driver_accepts_postgres(self):
        """Test that DB_DRIVER accepts 'postgres' value."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            postgres_password="test-password",
        )
        assert settings.db_driver == "postgres"

    def test_db_driver_case_insensitive(self):
        """Test that DB_DRIVER is case-insensitive."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="POSTGRES",
            postgres_password="test-password",
        )
        assert settings.db_driver == "postgres"

    def test_db_driver_rejects_invalid_value(self):
        """Test that DB_DRIVER rejects invalid values."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="mysql",
            )
        assert "DB_DRIVER must be either 'sqlite' or 'postgres'" in str(exc_info.value)

    def test_postgres_requires_password_or_url(self):
        """Test that DB_DRIVER=postgres requires either POSTGRES_PASSWORD or postgres DATABASE_URL."""
        # Should fail without password or postgres URL
        # Explicitly set postgres_password to None to override any environment variables
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="postgres",
                database_url=DEFAULT_SQLITE_URL,  # SQLite URL, not postgres
                postgres_password=None,  # Explicitly None to override env vars
            )
        assert "DB_DRIVER=postgres requires either DATABASE_URL" in str(exc_info.value)

    def test_postgres_with_password_succeeds(self):
        """Test that DB_DRIVER=postgres succeeds when POSTGRES_PASSWORD is provided."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            postgres_password="test-password",
        )
        assert settings.db_driver == "postgres"
        assert settings.postgres_password == "test-password"

    def test_postgres_with_database_url_postgresql_succeeds(self):
        """Test that DB_DRIVER=postgres succeeds when DATABASE_URL is a postgresql:// URL."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            database_url="postgresql://user:password@localhost:5432/journiv",
            postgres_password=None,  # Explicitly None to use DATABASE_URL instead
        )
        assert settings.db_driver == "postgres"
        assert settings.database_url.startswith("postgresql://")
        assert settings.effective_database_url.startswith("postgresql://")

    def test_postgres_with_database_url_postgres_scheme_succeeds(self):
        """Test that DB_DRIVER=postgres succeeds with 'postgres://' URL scheme."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            database_url="postgres://user:password@localhost:5432/journiv",
            postgres_password=None,  # Explicitly None to use DATABASE_URL instead
        )
        assert settings.db_driver == "postgres"
        assert settings.database_url.startswith("postgres://")
        assert settings.effective_database_url.startswith("postgres://")

    def test_postgres_with_database_url_succeeds(self):
        """Test that DB_DRIVER=postgres succeeds when DATABASE_URL is a postgres URL."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            database_url="postgresql://user:password@localhost:5432/journiv",
            postgres_password=None,  # Explicitly None to use DATABASE_URL instead
        )
        assert settings.db_driver == "postgres"
        assert settings.database_url.startswith("postgresql://")
        assert settings.effective_database_url.startswith("postgresql://")

    def test_postgres_rejects_empty_password(self):
        """Test that DB_DRIVER=postgres rejects empty POSTGRES_PASSWORD."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="postgres",
                postgres_password="",  # Empty password
            )
        assert "POSTGRES_PASSWORD cannot be empty" in str(exc_info.value)

    def test_postgres_rejects_whitespace_only_password(self):
        """Test that DB_DRIVER=postgres rejects whitespace-only POSTGRES_PASSWORD."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="postgres",
                postgres_password="   ",  # Whitespace only
            )
        assert "POSTGRES_PASSWORD cannot be empty" in str(exc_info.value)

    def test_sqlite_works_without_postgres_config(self):
        """Test that DB_DRIVER=sqlite works without any postgres configuration."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="sqlite",
            database_url=DEFAULT_SQLITE_URL,
        )
        assert settings.db_driver == "sqlite"
        assert settings.database_url == DEFAULT_SQLITE_URL

    def test_postgres_with_password_uses_defaults(self):
        """Test that DB_DRIVER=postgres with password uses defaults for host, user, db."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            postgres_password="test-password",
            environment="development",
        )
        assert settings.db_driver == "postgres"
        assert settings.postgres_password == "test-password"
        # Check that effective_database_url is constructed with defaults
        effective_url = settings.effective_database_url
        assert effective_url.startswith("postgresql://")
        assert "postgres" in effective_url  # default host
        assert "journiv" in effective_url  # default user
        assert "journiv_dev" in effective_url  # default db for development

    def test_postgres_with_password_production_defaults(self):
        """Test that DB_DRIVER=postgres with password uses production defaults."""
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            postgres_password="test-password",
            environment="production",
        )
        assert settings.db_driver == "postgres"
        effective_url = settings.effective_database_url
        assert "journiv_prod" in effective_url  # default db for production

    def test_postgres_validates_effective_url_is_postgres(self):
        """Test that DB_DRIVER=postgres validates effective URL is actually PostgreSQL."""
        # This should pass - postgres_password will make effective URL postgres
        settings = Settings(
            secret_key="test-secret-key-for-testing-only-32-chars",
            db_driver="postgres",
            postgres_password="test-password",
        )
        assert settings.db_driver == "postgres"
        assert settings.effective_database_url.startswith("postgresql://")

    def test_url_sanitization_in_error_messages(self):
        """Test that database URLs with credentials are sanitized to prevent password exposure."""
        # Test PostgreSQL URL with password - password should be masked
        postgres_url = "postgresql://user:secretpassword123@localhost:5432/dbname"
        sanitized = Settings._sanitize_url(postgres_url)

        # Verify password is not exposed
        assert "secretpassword123" not in sanitized, "Password exposed in sanitized URL!"
        # Verify URL is sanitized (should contain *** or similar)
        assert "***" in sanitized, f"URL not sanitized! Got: {sanitized}"

        # Test SQLite URL - should remain unchanged (no credentials to mask)
        sqlite_url = "sqlite:////data/journiv.db"
        sanitized_sqlite = Settings._sanitize_url(sqlite_url)
        assert sqlite_url == sanitized_sqlite, "SQLite URL should not be modified"

    def test_postgres_rejects_both_password_and_database_url(self):
        """Test that DB_DRIVER=postgres fails when both POSTGRES_PASSWORD and DATABASE_URL (postgres) are set."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="postgres",
                postgres_password="test-password",
                database_url="postgresql://user:password@localhost:5432/journiv",
            )
        error_message = str(exc_info.value)
        assert "Cannot specify both POSTGRES_PASSWORD and DATABASE_URL" in error_message

    def test_postgres_requires_either_password_or_database_url(self):
        """Test that DB_DRIVER=postgres requires either POSTGRES_PASSWORD or DATABASE_URL (postgres)."""
        # This test already exists as test_postgres_requires_password_or_url, but let's verify it still works
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret-key-for-testing-only-32-chars",
                db_driver="postgres",
                database_url=DEFAULT_SQLITE_URL,  # SQLite URL, not postgres
                postgres_password=None,  # Explicitly None to override env vars
            )
        assert "DB_DRIVER=postgres requires either DATABASE_URL" in str(exc_info.value)

