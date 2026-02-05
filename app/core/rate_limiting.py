"""
Rate limiting configuration and utilities.
"""
import logging
from copy import deepcopy

from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import slowapi, with fallback if not available
try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    logger.debug("slowapi not available in environment")

if settings.rate_limiting_enabled and not SLOWAPI_AVAILABLE:
    message = "slowapi is required for rate limiting but is not installed."
    if settings.environment == "production":
        raise RuntimeError(message)
    logger.warning("%s Rate limiting has been disabled.", message)

RATE_LIMITING_ACTIVE = settings.rate_limiting_enabled and SLOWAPI_AVAILABLE

# Rate limit configurations for different endpoints
# TODO: Make it configurable
DEFAULT_RATE_LIMITS = {
    # Authentication endpoints - more restrictive
    "auth": {
        "login": "5/minute",
        "register": "3/minute",
        "refresh": "10/minute",
        "logout": "20/minute"
    },

    # User endpoints - moderate limits
    "users": {
        "profile": "100/hour",
        "update": "20/hour",
        "delete": "1/hour"
    },

    # Journal endpoints - moderate limits
    "journals": {
        "create": "20/hour",
        "list": "200/hour",
        "update": "50/hour",
        "delete": "10/hour"
    },

    # Entry endpoints - higher limits for content creation
    "entries": {
        "create": "100/hour",
        "list": "500/hour",
        "search": "200/hour",
        "update": "100/hour",
        "delete": "50/hour"
    },

    # Media upload endpoints - restrictive due to file size
    "media": {
        "upload": "50/hour",
        "download": "1000/hour"
    },

    # Search endpoints - moderate limits
    "search": {
        "quick": "200/hour",
        "advanced": "100/hour",
        "suggestions": "500/hour"
    },

    # Analytics endpoints - lower limits due to computation
    "analytics": {
        "dashboard": "50/hour",
        "streak": "100/hour",
        "patterns": "30/hour"
    },

    # Tag endpoints - moderate limits
    "tags": {
        "create": "50/hour",
        "list": "200/hour",
        "search": "300/hour"
    },

    # Mood endpoints - moderate limits
    "moods": {
        "log": "100/hour",
        "list": "200/hour",
        "analytics": "50/hour"
    },

    # Prompt endpoints - moderate limits
    "prompts": {
        "daily": "10/hour",
        "random": "50/hour",
        "search": "200/hour"
    }
}

if settings.rate_limit_config:
    RATE_LIMITS = deepcopy(settings.rate_limit_config)
    logger.info("Applying rate limit configuration from settings.")
else:
    RATE_LIMITS = deepcopy(DEFAULT_RATE_LIMITS)


# Get default limits based on environment
def get_default_limits():
    """Get default rate limits based on environment."""
    if not settings.rate_limiting_enabled:
        return []

    if settings.rate_limit_default_limits:
        return settings.rate_limit_default_limits

    # Disable rate limiting during tests by default
    if settings.environment == "test":
        return ["1000/second"]
    return ["1000/hour"]  # Production default


# Initialize limiter only if rate limiting is active
limiter = None

def get_limiter():
    """Get the limiter instance, creating it if necessary."""
    global limiter
    if limiter is None or not settings.rate_limiting_enabled:
        if settings.rate_limiting_enabled and SLOWAPI_AVAILABLE:
            limiter = Limiter(
                key_func=get_remote_address,
                storage_uri=settings.rate_limit_storage_uri,
                default_limits=get_default_limits()
            )
        else:
            # Create a dummy limiter that doesn't do anything
            class DummyLimiter:
                def limit(self, *args, **kwargs):
                    def decorator(func):
                        return func
                    return decorator

            limiter = DummyLimiter()
            if settings.rate_limiting_enabled:
                logger.info("Rate limiting disabled: dependencies unavailable, using no-op limiter.")
            else:
                logger.info("Rate limiting disabled via configuration.")

    return limiter


def _fallback_limit() -> str:
    """Derive fallback limit for uncategorized endpoints."""
    if settings.rate_limit_default_limits:
        try:
            return settings.rate_limit_default_limits[0]
        except IndexError:
            pass
    if settings.environment == "test":
        return "1000/second"
    return "100/hour"


def get_rate_limit(endpoint_type: str, endpoint_name: str) -> str:
    """Get rate limit for specific endpoint."""
    if not settings.rate_limiting_enabled:
        return "1000/second"

    # Disable rate limiting during tests by returning a very high limit
    if settings.environment == "test":
        return "1000/second"

    fallback_limit = _fallback_limit()
    scope_limits = RATE_LIMITS.get(endpoint_type)

    if scope_limits is None:
        logger.warning(
            "No rate limit scope configured for '%s'. Using fallback limit %s.",
            endpoint_type,
            fallback_limit,
        )
        return fallback_limit

    limit = scope_limits.get(endpoint_name)
    if limit is None:
        logger.warning(
            "No rate limit entry configured for '%s.%s'. Using fallback limit %s.",
            endpoint_type,
            endpoint_name,
            fallback_limit,
        )
        return fallback_limit

    return limit

def rate_limit_exceeded_handler(request: Request, exc):
    """Custom rate limit exceeded handler."""
    from fastapi.responses import JSONResponse

    from app.middleware.request_logging import request_id_ctx

    request_id = request_id_ctx.get()
    if isinstance(exc, RateLimitExceeded):
        limit_detail = getattr(exc, "detail", None) or getattr(exc, "limit", "unknown")
    else:
        limit_detail = getattr(exc, "detail", "unknown")

    retry_after = getattr(exc, "retry_after", None)
    if retry_after is None:
        retry_after = getattr(exc, "reset_in", None)
    if retry_after is None:
        headers = getattr(exc, "headers", None)
        if isinstance(headers, dict):
            retry_after = headers.get("Retry-After")
    if retry_after is None:
        retry_after = 60

    logger.warning(
        f"Rate limit exceeded for request {request_id}",
        extra={
            "request_id": request_id,
            "client_ip": getattr(request.client, 'host', 'unknown'),
            "path": request.url.path,
            "limit": limit_detail
        }
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": f"Too many requests. Limit: {limit_detail}",
            "retry_after": retry_after,
            "request_id": request_id
        }
    )


# Rate limiting decorators for common patterns
def auth_rate_limit(endpoint: str):
    """Rate limit decorator for authentication endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("auth", endpoint))


def user_rate_limit(endpoint: str):
    """Rate limit decorator for user endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("users", endpoint))


def journal_rate_limit(endpoint: str):
    """Rate limit decorator for journal endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("journals", endpoint))


def entry_rate_limit(endpoint: str):
    """Rate limit decorator for entry endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("entries", endpoint))


def media_rate_limit(endpoint: str):
    """Rate limit decorator for media endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("media", endpoint))


def search_rate_limit(endpoint: str):
    """Rate limit decorator for search endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("search", endpoint))


def analytics_rate_limit(endpoint: str):
    """Rate limit decorator for analytics endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("analytics", endpoint))


def tag_rate_limit(endpoint: str):
    """Rate limit decorator for tag endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("tags", endpoint))


def mood_rate_limit(endpoint: str):
    """Rate limit decorator for mood endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("moods", endpoint))


def prompt_rate_limit(endpoint: str):
    """Rate limit decorator for prompt endpoints."""
    if not settings.rate_limiting_enabled:
        return lambda func: func  # No-op decorator
    return get_limiter().limit(get_rate_limit("prompts", endpoint))
