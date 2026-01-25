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

try:
    from sqlalchemy.engine import make_url
except ImportError:
    make_url = None

# Import version from package
# Using JOURNIV_VERSION (not APP_VERSION) to prevent APP_VERSION env var from overriding app_version field
from app import __version__ as JOURNIV_VERSION

logger = logging.getLogger(__name__)

# Insecure default that should never be used in production
_INSECURE_DEFAULT_SECRET = "your-super-secret-key-change-in-production"
DEFAULT_SQLITE_URL = "sqlite:////data/journiv.db"
REDIS_OIDC_REQUIRED_MSG = (
    "REDIS_URL must be provided when OIDC_ENABLED=true."
)

JOURNIV_PLUS_DOC_URL = "https://journiv.com/plus"
DEFAULT_PLUS_SERVER_URL = "https://plus.journiv.com"

# Define the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Journiv Service"
    # Version is forced from app.__init__.py via model_validator (see force_app_version_from_code)
    # This prevents APP_VERSION env var from overriding the code version
    app_version: str = ""  # Will be overridden by validator
    debug: bool = False
    environment: str = "development"
    domain_name: str = ""
    domain_scheme: str = "http"  # Protocol scheme: "http" (default, for development) or "https" (required for production, especially when behind reverse proxy). Used to generate correct public redirect URLs for OIDC callbacks and logout.

    # API
    api_v1_prefix: str = "/api/v1"
    enable_cors: bool = False
    cors_origins: Optional[List[str]] = None

    # Database Configuration
    # Database driver selection: "sqlite" (default) or "postgres"
    db_driver: str = "sqlite"

    # Primary database URL (defaults to SQLite, can be PostgreSQL URL when DB_DRIVER=postgres)
    database_url: str = DEFAULT_SQLITE_URL

    # Individual PostgreSQL components (optional - used in Docker)
    # When POSTGRES_PASSWORD is set, these components are used to construct the PostgreSQL URL
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
    oidc_redirect_uri: Optional[str] = None
    oidc_scopes: str = "openid email profile"
    oidc_auto_provision: bool = True
    oidc_disable_ssl_verify: bool = False  # Only for local development with self-signed certs
    oidc_allow_insecure_prod: bool = False  # Allow OIDC over HTTP (INSECURE). Recommended only for advanced users in isolated homelabs. Default: false

    # Redis Configuration (for OIDC state/cache and Celery)
    redis_url: Optional[str] = None  # e.g., "redis://localhost:6379/0"

    # Auth cache (short-lived) to reduce DB lookups during request bursts
    auth_user_cache_ttl_seconds: int = 60

    # Celery Configuration
    celery_broker_url: Optional[str] = None  # e.g., "redis://localhost:6379/0"
    celery_result_backend: Optional[str] = None  # e.g., "redis://localhost:6379/0"
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: List[str] = Field(default_factory=lambda: ["json"])
    celery_timezone: str = "UTC"
    celery_enable_utc: bool = True

    # Import/Export Configuration
    import_export_max_file_size_mb: int = 500  # Max size for import/export files
    export_cleanup_days: int = 7  # Days to keep export files before cleanup
    import_temp_dir: str = "/data/imports/temp"
    export_dir: str = "/data/exports"

    # Integrations Configuration
    # Base URLs for family-shared self-hosted services (optional defaults)
    immich_base_url: Optional[str] = None  # e.g., "https://photos.family.lan"
    jellyfin_base_url: Optional[str] = None  # e.g., "https://media.family.lan"
    audiobookshelf_base_url: Optional[str] = None  # e.g., "https://books.family.lan"

    # Integration sync settings
    integration_sync_interval_hours: int = 6  # How often to sync integrations
    integration_cache_limit: int = 1000  # Max cached items per user per integration

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
    media_signed_url_ttl_seconds: int = 300  # 5 minutes for images and general media
    media_signed_url_video_ttl_seconds: int = 1200  # 20 minutes for videos
    media_thumbnail_signed_url_ttl_seconds: int = 86400  # 24 hours for thumbnails
    media_signed_url_grace_seconds: int = 60 # 1 minute grace period
    export_signed_url_expiration_seconds: int = 3600  # 1 hour expiration for export downloads

    # File Processing Timeouts
    ffprobe_timeout: int = 300  # 5 minutes for video metadata extraction
    ffmpeg_timeout: int = 300   # 5 minutes for video thumbnail generation

    # Weather Configuration
    open_weather_api_key_25: Optional[str] = None  # OpenWeather 2.5 API key
    open_weather_api_key_30: Optional[str] = None  # OpenWeather 3.0 API key
    weather_provider: str = "openweather"  # Weather provider (openweather)

    @field_validator('open_weather_api_key_25', 'open_weather_api_key_30', mode='before')
    @classmethod
    def trim_weather_api_key(cls, v):
        """Trim whitespace from weather API keys."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() if v.strip() else None
        return v

    # Application configuration
    app_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    log_dir: str = "/data/logs"

    # Disable signup
    disable_signup: bool = Field(
        default_factory=lambda: os.getenv("DISABLE_SIGNUP", "false").lower() == "true"
    )

    # Rate limiting
    rate_limiting_enabled: bool = Field(
        default_factory=lambda: os.getenv("RATE_LIMITING_ENABLED", "false" if os.getenv("ENVIRONMENT") == "test" else "true").lower() == "true"
    )
    rate_limit_storage_uri: str = "memory://"
    rate_limit_default_limits: Optional[List[str]] = None
    rate_limit_config: Optional[Dict[str, Dict[str, str]]] = None

    # Journiv Plus Server integration
    plus_server_url: str = DEFAULT_PLUS_SERVER_URL

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_type(self) -> str:
        """Detect database type from effective database URL."""
        url = self.effective_database_url
        if url.startswith("sqlite"):
            return "sqlite"
        elif url.startswith(("postgresql", "postgres")):
            return "postgres"
        return "sqlite"

    @property
    def effective_database_url(self) -> str:
        """
        Get the effective database URL based on DB_DRIVER and configuration.

        When DB_DRIVER=postgres:
        - Either POSTGRES_PASSWORD (with components) OR DATABASE_URL (postgres URL) must be set
        - Not both - validation will fail if both are specified
        - If POSTGRES_PASSWORD is set, construct PostgreSQL URL from components
        - If DATABASE_URL is a PostgreSQL URL, use it directly

        When DB_DRIVER=sqlite:
        - Use DATABASE_URL (defaults to SQLite)
        """
        if self.db_driver == "postgres":
            has_postgres_password = self.postgres_password is not None and self.postgres_password.strip()
            has_postgres_database_url = self._is_postgres_url(self.database_url)

            # Check for mutual exclusivity (validation should catch this, but handle gracefully)
            if has_postgres_password and has_postgres_database_url:
                raise ValueError(
                    "Cannot specify both POSTGRES_PASSWORD and DATABASE_URL (postgres) when DB_DRIVER=postgres. "
                    "Use either POSTGRES_PASSWORD with or without components OR complete DATABASE_URL (postgres URL), not both."
                )

            # Use POSTGRES_PASSWORD to construct URL
            if has_postgres_password:
                host = self.postgres_host or "postgres"
                user = self.postgres_user or "journiv"
                default_db = "journiv_prod" if self.environment == "production" else "journiv_dev"
                db = self.postgres_db or default_db
                port = self.postgres_port or 5432
                return f"postgresql://{user}:{self.postgres_password}@{host}:{port}/{db}"

            # Use DATABASE_URL if it's a PostgreSQL URL
            if has_postgres_database_url:
                return self.database_url

            # Neither specified (validation should have caught this, but handle gracefully)
            raise ValueError(
                "When DB_DRIVER=postgres, either POSTGRES_PASSWORD or DATABASE_URL (postgres URL) must be set. "
                "Please configure one of these options."
            )

        # DB_DRIVER=sqlite: use DATABASE_URL (defaults to SQLite)
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

    @field_validator('postgres_port', mode='before')
    @classmethod
    def validate_postgres_port(cls, v) -> Optional[int]:
        """Validate PostgreSQL port, converting empty strings to None."""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            try:
                return int(v)
            except ValueError:
                return None
        if isinstance(v, int):
            return v
        return None

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
                "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
                "video/mp4", "video/avi", "video/mov", "video/quicktime", "video/webm", "video/x-m4v",
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
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic",
                ".mp4", ".avi", ".mov", ".webm", ".m4v",
                ".mp3", ".wav", ".ogg", ".m4a", ".aac"
            ]
        return v

    @staticmethod
    def _is_postgres_url(url: str) -> bool:
        """
        Check if a URL is a PostgreSQL URL.

        Recognizes standard PostgreSQL URLs and SQLAlchemy driver variants:
        - postgresql://
        - postgres://
        - postgresql+asyncpg://
        - postgresql+psycopg2://
        - postgresql+psycopg://
        - etc.
        """
        if not url:
            return False
        url = url.strip()
        if not url:
            return False

        # Try to use SQLAlchemy's URL parser for proper detection (handles driver variants)
        if make_url is not None:
            try:
                parsed = make_url(url)
                driver_name = parsed.drivername or ""
                # Remove driver suffix (e.g., "postgresql+asyncpg" -> "postgresql")
                base_driver = driver_name.split("+", 1)[0].lower()
                return base_driver in ("postgresql", "postgres")
            except Exception as exc:  # noqa: BLE001
                # Avoid logging the URL or exception message; only log the type.
                logger.debug(
                    "Failed to parse database URL with SQLAlchemy (%s); falling back to scheme parsing.",
                    type(exc).__name__,
                )

        try:
            scheme = url.split("://", 1)[0].lower()
            base_scheme = scheme.split("+", 1)[0]
            return base_scheme in ("postgresql", "postgres")
        except (ValueError, IndexError):
            return False

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """
        Sanitize a database URL by hiding credentials.

        Returns a safe version of the URL with password masked, suitable for
        logging and error messages. Falls back to manual masking if SQLAlchemy
        URL parsing fails.
        """
        if not url:
            return "<empty>"

        url = url.strip()
        if not url:
            return "<empty>"

        # Try to use SQLAlchemy's URL parser for proper sanitization
        if make_url is not None:
            try:
                parsed = make_url(url)
                return parsed.render_as_string(hide_password=True)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Failed to sanitize database URL with SQLAlchemy (%s); falling back to manual masking.",
                    type(exc).__name__,
                )

        # Fallback: manually mask password if present
        # Pattern: scheme://user:password@host/path
        if "@" in url and "://" in url:
            try:
                scheme_part, rest = url.split("://", 1)
                if "@" in rest:
                    user_pass, host_part = rest.rsplit("@", 1)
                    if ":" in user_pass:
                        user, _ = user_pass.split(":", 1)
                        return f"{scheme_part}://{user}:***@{host_part}"
                    return f"{scheme_part}://{user_pass}@{host_part}"
            except (ValueError, IndexError):
                pass

        # If no credentials detected, return as-is (safe for SQLite)
        return url

    @field_validator('db_driver')
    @classmethod
    def validate_db_driver(cls, v: str) -> str:
        """Validate DB_DRIVER is either sqlite or postgres."""
        if isinstance(v, str):
            v = v.lower().strip()
        if v not in ("sqlite", "postgres"):
            raise ValueError(
                "DB_DRIVER must be either 'sqlite' or 'postgres'. "
                f"Got: {v}"
            )
        return v

    @field_validator('domain_scheme')
    @classmethod
    def validate_domain_scheme(cls, v: str) -> str:
        """Validate DOMAIN_SCHEME is either http or https."""
        v = v.lower().strip()
        if v not in ("http", "https"):
            raise ValueError(
                "DOMAIN_SCHEME must be either 'http' or 'https'. "
                f"Got: {v}"
            )
        return v

    @field_validator('domain_name')
    @classmethod
    def validate_domain_name(cls, v: str) -> str:
        """Validate DOMAIN_NAME does not contain scheme or trailing slash."""
        if not v:
            return v

        v = v.strip()

        # Check for scheme prefix
        if v.startswith("http://") or v.startswith("https://"):
            raise ValueError(
                "DOMAIN_NAME must not contain a scheme (http:// or https://). "
                "Set the scheme separately using DOMAIN_SCHEME. "
                f"Got: {v}"
            )

        # Remove trailing slash if present
        if v.endswith("/"):
            v = v.rstrip("/")
            logger.warning(
                f"DOMAIN_NAME had trailing slash removed: {v}"
            )

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

    @field_validator('media_signed_url_grace_seconds')
    @classmethod
    def validate_grace_period(cls, v: int, info: ValidationInfo) -> int:
        """Validate grace period is reasonable."""
        if v < 0:
            raise ValueError("Grace period must be non-negative")
        if v > 300:  # 5 minutes max
            raise ValueError("Grace period cannot exceed 300 seconds (5 minutes)")

        # Validate grace period is shorter than all media TTLs
        ttl = info.data.get('media_signed_url_ttl_seconds', 300)
        video_ttl = info.data.get('media_signed_url_video_ttl_seconds', 1200)
        thumb_ttl = info.data.get('media_thumbnail_signed_url_ttl_seconds', 86400)

        min_ttl = min(ttl, video_ttl, thumb_ttl)

        if v >= min_ttl:
            raise ValueError(
                f"Grace period ({v}s) must be shorter than the minimum media TTL ({min_ttl}s)"
            )

        return v

    @field_validator('celery_broker_url', 'celery_result_backend')
    @classmethod
    def validate_celery_urls(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        """Auto-configure Celery from redis_url if not explicitly set."""
        if v:
            return v

        field_name = info.field_name
        redis_url = info.data.get('redis_url')

        # If redis_url is set, use it as default for Celery
        if redis_url and not v:
            field_display = field_name.upper() if field_name else "CELERY_URL"
            logger.info(
                f"{field_display} not set. Defaulting to REDIS_URL: {redis_url}"
            )
            return redis_url

        return v

    @model_validator(mode='after')
    def force_app_version_from_code(self) -> 'Settings':
        """Force app_version to always use the version from code, ignoring env vars."""
        self.app_version = JOURNIV_VERSION
        return self

    @model_validator(mode='after')
    def construct_oidc_redirect_uri(self) -> 'Settings':
        """Construct oidc_redirect_uri from domain components if not explicitly set."""
        if not self.oidc_redirect_uri:
            if self.domain_name:
                self.oidc_redirect_uri = f"{self.domain_scheme}://{self.domain_name}{self.api_v1_prefix}/auth/oidc/callback"
            else:
                self.oidc_redirect_uri = f"{self.domain_scheme}://localhost:{self.app_port}{self.api_v1_prefix}/auth/oidc/callback"
        return self

    @model_validator(mode='after')
    def validate_db_driver_requirements(self) -> 'Settings':
        """
        Validate that required database configuration is provided when DB_DRIVER=postgres.

        This validator ensures that when DB_DRIVER=postgres:
        - Either a PostgreSQL DATABASE_URL or POSTGRES_PASSWORD is provided
        - The effective database URL will be PostgreSQL
        - Empty passwords are rejected

        Runs before validate_production_settings to ensure DB_DRIVER is properly configured.
        """
        if self.db_driver != "postgres":
            return self

        # Check if postgres_password is explicitly set but empty
        if self.postgres_password is not None and not self.postgres_password.strip():
            raise ValueError(
                "POSTGRES_PASSWORD cannot be empty when DB_DRIVER=postgres. "
                "Please provide a valid password."
            )

        # Check if we have a PostgreSQL URL in DATABASE_URL
        has_postgres_url = self._is_postgres_url(self.database_url)

        # Check if we have PostgreSQL components (POSTGRES_PASSWORD)
        has_postgres_components = (
            self.postgres_password is not None and self.postgres_password.strip()
        )

        # Require exactly one: either POSTGRES_PASSWORD or DATABASE_URL (postgres), not both, not neither
        if has_postgres_components and has_postgres_url:
            raise ValueError(
                "DB_DRIVER=postgres: Cannot specify both POSTGRES_PASSWORD and DATABASE_URL (postgres URL). "
                "Use either POSTGRES_PASSWORD with components or without components OR complete DATABASE_URL (postgres URL), not both."
            )

        if not (has_postgres_url or has_postgres_components):
            raise ValueError(
                "DB_DRIVER=postgres requires either DATABASE_URL (with postgresql:// or postgres://) "
                "or POSTGRES_PASSWORD to be set. "
                "When using POSTGRES_PASSWORD, host, user, and db can use defaults."
            )

        # Verify that the effective database URL will be PostgreSQL
        # This ensures consistency between DB_DRIVER setting and actual database connection
        effective_url = self.effective_database_url
        if not self._is_postgres_url(effective_url):
            safe_url = self._sanitize_url(effective_url)
            raise ValueError(
                f"DB_DRIVER=postgres is set, but effective database URL is not PostgreSQL: {safe_url}. "
                "Please configure PostgreSQL connection settings."
            )

        return self

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

        # OIDC validation
        if self.oidc_enabled:
            if not self.domain_name:
                errors.append(
                    "DOMAIN_NAME must be set when OIDC_ENABLED=true in production. "
                    "The OIDC redirect URI must point to your production domain."
                )
            if self.oidc_redirect_uri and 'localhost' in self.oidc_redirect_uri:
                errors.append(
                    "OIDC_REDIRECT_URI contains 'localhost' in production. "
                    "Set DOMAIN_NAME or explicitly configure OIDC_REDIRECT_URI to your production domain."
                )
            if self.oidc_client_secret == "change_me":
                errors.append(
                    "OIDC_CLIENT_SECRET must be changed from default value in production."
                )
            if self.oidc_disable_ssl_verify:
                errors.append(
                    "OIDC_DISABLE_SSL_VERIFY must be False in production. "
                    "Never disable SSL verification in production environments."
                )

        # Check database configuration
        if self.db_driver == "postgres":
            # DB_DRIVER=postgres should already be validated, but double-check
            if not self._is_postgres_url(self.effective_database_url):
                errors.append(
                    "DB_DRIVER=postgres is set but effective database URL is not PostgreSQL. "
                    "This should have been caught by validation."
                )
        elif self.database_url.startswith("sqlite") and not (
            self.postgres_host and self.postgres_user and self.postgres_db
        ):
            warnings.append(
                "Using SQLite in production. Ensure you understand the durability "
                "limitations and configure regular backups."
            )

        # Check Celery configuration for import/export
        if not self.celery_broker_url:
            warnings.append(
                "CELERY_BROKER_URL not configured. Import/export features require Celery with Redis."
            )
        if not self.celery_result_backend:
            warnings.append(
                "CELERY_RESULT_BACKEND not configured. Job status tracking will not work."
            )

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

    @model_validator(mode='after')
    def validate_oidc_redis_requirement(self) -> 'Settings':
        """Validate that Redis URL is provided when OIDC is enabled."""
        if self.oidc_enabled:
            if not self.redis_url or not self.redis_url.strip():
                raise ValueError(REDIS_OIDC_REQUIRED_MSG)
        return self

    @model_validator(mode='after')
    def validate_oidc_http_safety(self) -> 'Settings':
        """Validate OIDC cannot be used over HTTP unless explicitly allowed."""
        if self.oidc_enabled and self.domain_scheme == "http":
            if not self.oidc_allow_insecure_prod:
                raise RuntimeError(
                    "OIDC cannot be used over HTTP. "
                    "Enable HTTPS or set OIDC_ALLOW_INSECURE_PROD=true to override."
                )
            logger.warning(
                "OIDC_ALLOW_INSECURE_PROD=true — running OIDC over HTTP is insecure and not recommended."
            )
        return self


# Create settings instance
settings = Settings()


# Version check constants can be modified later by admin.
VERSION_CHECK_ENABLED = True
VERSION_CHECK_INTERVAL_HOURS = 12
# Cache TTL: 4x the check interval (longer than check interval to ensure availability)
# This ensures cached data is available even if checks are delayed
VERSION_CHECK_CACHE_TTL = int(VERSION_CHECK_INTERVAL_HOURS * 4 * 3600)  # 4x interval in seconds

# License refresh constants
LICENSE_REFRESH_INTERVAL_HOURS = 6

# License cache constants
# Cache TTL: 8 hours (28800 seconds)
LICENSE_CACHE_TTL = 28800


def get_settings() -> Settings:
    """Get settings instance."""
    return settings
