"""
Application configuration using pydantic-settings.
"""
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import field_validator, model_validator, ValidationInfo, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Insecure default that should never be used in production
_INSECURE_DEFAULT_SECRET = "your-super-secret-key-change-in-production"
DEFAULT_SQLITE_URL = "sqlite:////data/journiv.db"

# Define the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Journiv Service"
    app_version: str = "0.1.0-beta.4"
    debug: bool = False
    environment: str = "development"
    domain_name: str = ""

    # API
    api_v1_prefix: str = "/api/v1"
    enable_cors: bool = False
    cors_origins: Optional[List[str]] = None

    # Database Configuration
    # Primary database URL (defaults to SQLite)
    database_url: str = DEFAULT_SQLITE_URL

    # PostgreSQL override (optional - for advanced users)
    postgres_url: Optional[str] = None

    # Individual PostgreSQL components (optional - used in Docker)
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_db: Optional[str] = None
    postgres_host: Optional[str] = None
    postgres_port: Optional[int] = None


    # Security
    secret_key: str = ""  # Must be set via environment variable
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # OIDC Configuration
    oidc_enabled: bool = False
    oidc_issuer: str = "https://pocketid.example.com"
    oidc_client_id: str = "journiv-app"
    oidc_client_secret: str = "change_me"
    oidc_redirect_uri: str = "https://localhost:8000/api/v1/auth/oidc/callback"
    oidc_scopes: str = "openid email profile"
    oidc_auto_provision: bool = True
    oidc_disable_ssl_verify: bool = False  # Only for local development with self-signed certs

    # Redis Configuration (for OIDC state/cache)
    redis_url: Optional[str] = None  # e.g., "redis://localhost:6379/0"

    # CSP Configuration
    enable_csp: bool = True
    enable_hsts: bool = True
    enable_csp_reporting: bool = True
    csp_report_uri: Optional[str] = None

    # File Storage
    media_root: str = "/data/media"
    # media_url_prefix: str = "/media"
    max_file_size_mb: int = 100
    allowed_media_types: Optional[List[str]] = None
    allowed_file_extensions: Optional[List[str]] = None

    # File Processing Timeouts
    ffprobe_timeout: int = 300  # 5 minutes for video metadata extraction
    ffmpeg_timeout: int = 300   # 5 minutes for video thumbnail generation


    # Application configuration
    app_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    log_dir: str = "/data/logs"


    # Rate limiting
    rate_limiting_enabled: bool = Field(
        default_factory=lambda: os.getenv("RATE_LIMITING_ENABLED", "false" if os.getenv("ENVIRONMENT") == "test" else "true").lower() == "true"
    )
    rate_limit_storage_uri: str = "memory://"
    rate_limit_default_limits: Optional[List[str]] = None
    rate_limit_config: Optional[Dict[str, Dict[str, str]]] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_type(self) -> str:
        """Detect database type from configuration."""
        # Check if PostgreSQL override is configured
        if self.postgres_url or (self.postgres_host and self.postgres_user):
            return "postgresql"

        # Check if primary database URL is PostgreSQL
        if self.database_url.startswith(("postgresql", "postgres")):
            return "postgresql"

        # Default to SQLite
        return "sqlite"

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL based on configuration hierarchy."""
        # Priority 1: Explicit PostgreSQL URL
        if self.postgres_url:
            return self.postgres_url

        # Priority 2: PostgreSQL components (Docker environment)
        if self.postgres_host and self.postgres_user and self.postgres_db:
            password = self.postgres_password or ""
            port = self.postgres_port or 5432
            return f"postgresql://{self.postgres_user}:{password}@{self.postgres_host}:{port}/{self.postgres_db}"

        # Priority 3: Primary database URL (defaults to SQLite)
        return self.database_url

    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Validate SECRET_KEY is set and secure."""
        if not v:
            env = info.data.get('environment', 'development')
            if env == 'production':
                raise ValueError(
                    "SECRET_KEY must be set in production! "
                    "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )
            else:
                # Development or other environments
                logger.warning(
                    "SECRET_KEY not set! Using auto-generated key for development. "
                    "This key will change on restart. Set SECRET_KEY in .env for persistence."
                )
                return secrets.token_urlsafe(32)

        # Validate minimum length (32 bytes = 43 chars in urlsafe base64)
        # Warn if using the insecure default
        if v == _INSECURE_DEFAULT_SECRET:
            logger.warning(
                "Using insecure default SECRET_KEY! "
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))' or openssl rand -hex 32"
            )
        elif len(v) < 32:
            logger.warning(
                f"SECRET_KEY is only {len(v)} characters long. "
                "Recommend at least 32 characters for security. "
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))' or openssl rand -hex 32"
            )

        return v

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        # Handle None or empty values
        if v is None:
            return []

        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                return []
            # Handle comma-separated string from env
            return [origin.strip() for origin in v.split(',') if origin.strip()]

        # Handle list
        if isinstance(v, list):
            return v

        # Default to empty list for any other type
        return []

    @field_validator('cors_origins')
    @classmethod
    def validate_cors_origins(cls, v: Optional[List[str]], info: ValidationInfo) -> List[str]:
        """Validate CORS origins for production."""
        v = v or []
        env = info.data.get('environment', 'development')
        enable_cors = info.data.get('enable_cors', False)

        # In production: require explicit configuration
        if env == 'production':
            if not enable_cors:
                return []
            if not v:
                raise ValueError(
                    "CORS_ORIGINS must be configured in production! "
                    "Set to your frontend domain(s), e.g., CORS_ORIGINS=https://yourdomain.com"
                )

            # Check for wildcard in production
            if '*' in v:
                logger.error(
                    "Wildcard (*) CORS origin not allowed in production! "
                    "Specify exact domains, e.g., https://yourdomain.com"
                )

            # Warn about http in production
            for origin in v:
                if origin.startswith('http://') and not origin.startswith('http://localhost'):
                    logger.warning(
                        f"HTTP origin '{origin}' in production! "
                        "Consider using HTTPS for security."
                    )
        else:
            # Development: provide defaults if empty and CORS is enabled
            if enable_cors and not v:
                return ["http://localhost:3000", "http://localhost:8080"]

        return v

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: str, info: ValidationInfo) -> str:
        """Validate primary database URL."""
        if not v or not v.strip():
            logger.info(
                "DATABASE_URL not provided; defaulting to SQLite at %s", DEFAULT_SQLITE_URL
            )
            return DEFAULT_SQLITE_URL

        url = v.strip()
        env = info.data.get('environment', 'development')

        if url.startswith("sqlite"):
            if env == 'production':
                logger.warning(
                    "Using SQLite in production. Ensure you understand the durability "
                    "limitations and configure regular backups."
                )
            return url

        if url.startswith(("postgresql", "postgres")):
            if env == 'production' and 'journiv_password' in url.lower():
                raise ValueError(
                    "Default database password detected in production! "
                    "Set a secure POSTGRES_PASSWORD in .env"
                )

            # Check for localhost in production
            if env == 'production' and ('localhost' in url or '127.0.0.1' in url):
                logger.warning(
                    "Database URL contains localhost in production. "
                    "Ensure this is intentional."
                )

            return url

        logger.warning(
            "DATABASE_URL uses unsupported or untested dialect '%s'. Proceed with caution.",
            url.split("://", 1)[0]
        )
        return url

    @field_validator('postgres_url')
    @classmethod
    def validate_postgres_url(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        """Validate PostgreSQL override URL."""
        if not v or not v.strip():
            return None

        url = v.strip()
        env = info.data.get('environment', 'development')

        if not url.startswith(("postgresql", "postgres")):
            raise ValueError(
                "POSTGRES_URL must be a PostgreSQL URL (postgresql:// or postgres://)"
            )

        if env == 'production' and 'journiv_password' in url.lower():
            raise ValueError(
                "Default database password detected in production! "
                "Set a secure POSTGRES_PASSWORD in .env"
            )

        # Check for localhost in production
        if env == 'production' and ('localhost' in url or '127.0.0.1' in url):
                    logger.warning(
                "PostgreSQL URL contains localhost in production. "
                "Ensure this is intentional."
            )

        return url

    @field_validator('allowed_media_types', 'allowed_file_extensions', mode='before')
    @classmethod
    def parse_list_fields(cls, v):
        """Parse list fields from string or list."""
        # Handle None
        if v is None:
            return None

        if isinstance(v, str):
            if not v.strip():
                return None
            # Remove brackets if present
            v = v.strip('[]')
            return [item.strip().strip('"').strip("'") for item in v.split(',') if item.strip()]

        if isinstance(v, list):
            return v

        return None

    @field_validator('allowed_media_types')
    @classmethod
    def validate_allowed_media_types(cls, v: Optional[List[str]]) -> List[str]:
        """Provide defaults for allowed_media_types if not set."""
        if v is None or not v:
            return [
                "image/jpeg", "image/png", "image/gif", "image/webp",
                "video/mp4", "video/avi", "video/mov", "video/webm",
                "audio/mpeg", "audio/wav", "audio/ogg", "audio/m4a", "audio/aac"
            ]
        return v

    @field_validator('rate_limit_default_limits', mode='before')
    @classmethod
    def parse_rate_limit_default_limits(cls, v):
        """Parse rate limit defaults specified as string."""
        return cls.parse_list_fields(v)

    @field_validator('rate_limit_config', mode='before')
    @classmethod
    def parse_rate_limit_config(cls, v):
        """Parse nested rate limit configuration."""
        if v in (None, "", {}):
            return None

        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON for RATE_LIMIT_CONFIG: {exc}") from exc
        elif isinstance(v, dict):
            parsed = v
        else:
            raise ValueError("RATE_LIMIT_CONFIG must be a dict or JSON string.")

        # Ensure nested dict[str, dict[str, str]]
        cleaned: Dict[str, Dict[str, str]] = {}
        for scope, limits in parsed.items():
            if not isinstance(limits, dict):
                raise ValueError(f"Rate limit scope '{scope}' must map to an object of endpoint limits.")
            cleaned[scope] = {}
            for endpoint, limit in limits.items():
                if not isinstance(limit, str):
                    raise ValueError(f"Rate limit for {scope}.{endpoint} must be a string like '5/minute'.")
                cleaned[scope][endpoint] = limit

        return cleaned

    @field_validator('allowed_file_extensions')
    @classmethod
    def validate_allowed_file_extensions(cls, v: Optional[List[str]]) -> List[str]:
        """Provide defaults for allowed_file_extensions if not set."""
        if v is None or not v:
            return [
                ".jpg", ".jpeg", ".png", ".gif", ".webp",
                ".mp4", ".avi", ".mov", ".webm",
                ".mp3", ".wav", ".ogg", ".m4a", ".aac"
            ]
        return v

    @field_validator('ffprobe_timeout', 'ffmpeg_timeout')
    @classmethod
    def validate_timeout_settings(cls, v: int) -> int:
        """Validate timeout settings are reasonable."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        if v > 3600:  # 1 hour max
            raise ValueError("Timeout cannot exceed 3600 seconds (1 hour)")
        return v

    @model_validator(mode='after')
    def validate_production_settings(self) -> 'Settings':
        """Comprehensive production validation."""
        if self.environment != "production":
            return self

        errors = []
        warnings = []

        # Critical checks
        if self.debug:
            errors.append("DEBUG must be False in production.")

        if self.enable_cors and not self.cors_origins:
            errors.append("CORS_ORIGINS must be configured when CORS is enabled.")

        # Security warnings
        if self.access_token_expire_minutes > 60:
            warnings.append(
                f"ACCESS_TOKEN_EXPIRE_MINUTES is {self.access_token_expire_minutes}. "
                "Consider using a shorter expiration time (e.g., 15-30 minutes)."
            )

        if self.max_file_size_mb > 100:
            warnings.append(
                f"MAX_FILE_SIZE_MB is {self.max_file_size_mb}MB. "
                "Large file uploads may cause memory issues. Consider reducing the limit."
            )

        # Log warnings
        for warning in warnings:
                    logger.warning(f"Production configuration warning: {warning}")

        # Raise a single error with all issues
        if errors:
            error_message = "Production configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_message)

        return self


# Create settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance."""
    return settings
