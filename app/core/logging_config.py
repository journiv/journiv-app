"""
Simple logging configuration.
"""
import logging
import logging.handlers
from enum import Enum
from pathlib import Path


class LogCategory(str, Enum):
    """Enumeration for standardized log categories."""
    APP = "app"
    REQUEST = "app.request"
    USER_ACTIONS = "app.user_actions"
    API_REQUESTS = "app.api_requests"
    FILE_UPLOADS = "app.file_uploads"
    ERRORS = "app.errors"
    DB = "app.db"
    SECURITY = "app.security"


DEFAULT_LOG_LEVEL = logging.INFO

# Fields that should be masked in logs
SENSITIVE_FIELDS = {
    'password',
    'currentpassword',
    'newpassword',
    'confirmpassword',
    'token',
    'accesstoken',
    'refreshtoken',
    'authorization',
    'secret',
    'secret_key',
    'secretkey',
    'api_key',
    'apikey',
    'database_url',
    'databaseurl',
    'postgres_password',
    'postgrespassword',
    'redis_url',
    'redisurl',
    'celery_broker_url',
    'celerybrokerurl',
    'oidc_client_secret',
    'oidcclientsecret',
}


def _sanitize_data(data):
    """
    Sanitize data to mask sensitive fields, similar to frontend _sanitizeData.

    Recursively processes dictionaries, lists, and strings to mask sensitive information.
    For URLs, attempts to mask credentials in connection strings.

    Args:
        data: Data to sanitize (dict, list, str, or any other type)

    Returns:
        Sanitized version of the data with sensitive fields masked
    """
    if data is None:
        return data

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            # Check if key matches any sensitive field (case-insensitive)
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                sanitized[key] = '***MASKED***'
            else:
                sanitized[key] = _sanitize_data(value)
        return sanitized

    if isinstance(data, list):
        return [_sanitize_data(item) for item in data]

    if isinstance(data, str):
        # Check if it's a URL with credentials that should be sanitized
        if '@' in data and '://' in data:
            # Try to mask credentials in URLs (postgresql://, redis://, etc.)
            try:
                scheme_part, rest = data.split('://', 1)
                if '@' in rest:
                    user_pass, host_part = rest.rsplit('@', 1)
                    if ':' in user_pass:
                        user, _ = user_pass.split(':', 1)
                        return f"{scheme_part}://{user}:***@{host_part}"
                    return f"{scheme_part}://{user_pass}@{host_part}"
            except (ValueError, IndexError):
                pass

        # Check if the entire string looks like a sensitive value
        # (e.g., long random strings that might be tokens)
        if len(data) > 32 and all(c.isalnum() or c in '-_' for c in data):
            # Might be a token/secret, but don't mask short strings or normal text
            # Only mask if it's a very long alphanumeric string
            if len(data) > 64:
                return '***MASKED***'

        return data

    # For other types, return as-is
    return data


def _resolve_log_level(level_value, default=DEFAULT_LOG_LEVEL):
    """Resolve string/integer log level inputs to a logging level."""
    if isinstance(level_value, str):
        candidate = level_value.strip()
        if not candidate:
            return default, True
        if candidate.isdigit():
            level_value = int(candidate)
        else:
            candidate = candidate.upper()
            try:
                return logging._checkLevel(candidate), False
            except (ValueError, TypeError):
                return default, True
    try:
        return logging._checkLevel(level_value), False
    except (ValueError, TypeError):
        return default, True


def _get_settings():
    """Lazy import to avoid circular dependency with config module."""
    from app.core.config import settings  # local import to break circular dependency
    return settings


def setup_logging():
    """Setup logging configuration."""
    settings = _get_settings()
    # Create logs directory

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    resolved_level, used_default_level = _resolve_log_level(settings.log_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (for Docker)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(resolved_level)

    # File handler (for local inspection)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(resolved_level)

    # Configure root logger
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Configure specific loggers
    logging.getLogger(LogCategory.APP).setLevel(resolved_level)
    logging.getLogger(LogCategory.DB).setLevel(logging.INFO)
    logging.getLogger(LogCategory.SECURITY).setLevel(logging.INFO)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    # Log configuration
    logger = logging.getLogger(__name__)
    if used_default_level:
        logger.warning(
            "Invalid log level '%s' in configuration, falling back to INFO",
            settings.log_level
        )
    logger.info(
        "Logging configured - Level: %s",
        logging.getLevelName(resolved_level)
    )
    logger.info(f"Console logging: Enabled")
    logger.info(f"File logging: {log_dir / 'app.log'}")


def get_request_logger():
    """
    Get a logger for request-specific logging.
    """
    from app.middleware.request_logging import RequestContextLogger
    return RequestContextLogger(LogCategory.REQUEST)


def _log_with_context(logger: logging.Logger, level: int, message: str, request_id: str = None, exc_info: bool = False, **kwargs):
    """Internal helper to format logs with an optional request ID and extra context.

    Args:
        logger: Logger instance to use
        level: Logging level
        message: Log message
        request_id: Optional request ID for context
        exc_info: Whether to include exception traceback
        **kwargs: Additional context to append to message (e.g., media_id, user_id)
                   Sensitive fields will be automatically masked
    """
    # Build the log message with request ID
    log_message = f"[{request_id}] {message}" if request_id else message

    # Append any extra context to the message (with sanitization)
    if kwargs:
        sanitized_kwargs = _sanitize_data(kwargs)
        extra_context = ", ".join(f"{k}={v}" for k, v in sanitized_kwargs.items())
        log_message = f"{log_message} ({extra_context})"

    # Call logger with only supported parameters
    logger.log(level, log_message, exc_info=exc_info)


def log_user_action(user_email: str, action: str, request_id: str = None, **kwargs):
    """Log user actions with request ID."""
    logger = logging.getLogger(LogCategory.USER_ACTIONS)
    message = f"User {user_email} {action}"
    _log_with_context(logger, logging.INFO, message, request_id, **kwargs)


def log_api_request(method: str, path: str, status_code: int, duration_ms: float, request_id: str = None, user_email: str = None):
    """Log API requests with request ID."""
    logger = logging.getLogger(LogCategory.API_REQUESTS)
    user_info = f" (user: {user_email})" if user_email else ""
    message = f"{method} {path} - {status_code} - {duration_ms}ms{user_info}"
    _log_with_context(logger, logging.INFO, message, request_id)


def log_file_upload(filename: str, file_size: int, success: bool, request_id: str = None, user_email: str = None):
    """Log file uploads with request ID."""
    logger = logging.getLogger(LogCategory.FILE_UPLOADS)
    status = "successful" if success else "failed"
    user_info = f" (user: {user_email})" if user_email else ""
    message = f"File upload {status}: {filename} ({file_size} bytes){user_info}"
    _log_with_context(logger, logging.INFO, message, request_id)


def log_info(message: str, request_id: str = None, **kwargs):
    """Log info messages with request ID."""
    logger = logging.getLogger(LogCategory.APP)
    _log_with_context(logger, logging.INFO, message, request_id, **kwargs)


def log_warning(message: str, request_id: str = None, **kwargs):
    """Log warning messages with request ID."""
    logger = logging.getLogger(LogCategory.APP)
    _log_with_context(logger, logging.WARNING, message, request_id, **kwargs)


def log_error(error: Exception | str, request_id: str = None, user_email: str = None, **kwargs):
    """Log errors with request ID.

    Args:
        error: Exception object or error message string
        request_id: Optional request ID for context
        user_email: Optional user email for context
        **kwargs: Additional context (e.g., media_id, user_id)
    """
    logger = logging.getLogger(LogCategory.ERRORS)
    user_info = f" (user: {user_email})" if user_email else ""
    message = f"Error: {str(error)}{user_info}"
    # exc_info should only be True if we have an actual Exception
    exc_info = isinstance(error, Exception)
    _log_with_context(logger, logging.ERROR, message, request_id, exc_info=exc_info, **kwargs)
