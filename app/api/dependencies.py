"""
Shared API dependencies.
"""
import hashlib
import logging
from typing import Annotated, Optional, Callable

from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, ExpiredSignatureError
from sqlmodel import Session

from app.core.config import JOURNIV_PLUS_DOC_URL, settings
from app.core.scoped_cache import ScopedCache
from app.core.database import get_session
from app.core.security import verify_token
from app.middleware.request_logging import request_id_ctx
from app.models.user import User
from app.models.enums import UserRole
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Alias for database session dependency
get_db = get_session

_user_cache: Optional[ScopedCache] = None


def _get_user_cache() -> Optional[ScopedCache]:
    if not settings.redis_url:
        return None
    global _user_cache
    if _user_cache is None:
        _user_cache = ScopedCache(namespace="user_cache")
    return _user_cache


def get_request_id() -> str:
    """
    Dependency to get the current request ID from context.

    This can be used in endpoints to access the request ID for logging or other purposes.

    Usage:
        @router.get("/example")
        async def example(request_id: Annotated[str, Depends(get_request_id)]):
            logger.info(f"Processing request {request_id}")

    Returns:
        The current request ID, or 'unknown' if not in a request context.
    """
    return request_id_ctx.get()


async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    cookie_token: Annotated[Optional[str], Cookie(alias="access_token")] = None,
    session: Annotated[Session, Depends(get_session)] = None
) -> User:
    """
    Dependency to get the current authenticated user from the token.
    Raises HTTPException with status 401 if authentication fails or token is revoked.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Use token from Authorization header or cookie (web video streaming)
    token_to_use = token or cookie_token
    if token_to_use is None:
        raise credentials_exception

    try:
        # Verify token signature and expiration
        payload = verify_token(token_to_use, "access")
        user_id: str = payload.get("sub")

        # Validate claim types
        if not isinstance(user_id, str) or not user_id:
            raise credentials_exception

    except HTTPException:
        raise
    except ExpiredSignatureError:
        logger.info("Expired token presented", extra={"user_id": locals().get('user_id')})
        raise credentials_exception
    except JWTError as e:
        logger.warning("JWT error during token validation", extra={"error": str(e)})
        raise credentials_exception
    except Exception as e:
        logger.error("Unexpected token validation error", extra={"error": str(e)})
        raise credentials_exception

    token_hash = hashlib.sha256(token_to_use.encode("utf-8")).hexdigest()
    cache = _get_user_cache()
    if cache:
        deleted_marker = cache.get(scope_id=user_id, cache_type="deleted")
        if deleted_marker:
            raise credentials_exception
        cached_user = cache.get(scope_id=token_hash, cache_type="auth")
        if cached_user:
            try:
                user = User.model_validate(cached_user)
                if not user.is_active:
                    raise credentials_exception
                return user
            except Exception:
                cache.delete(scope_id=token_hash, cache_type="auth")

    # Get user from database
    user = UserService(session).get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    # Check if user is active
    if not user.is_active:
        logger.info("Inactive user access attempt", extra={"user_id": user_id})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    if cache:
        cache.set(
            scope_id=token_hash,
            cache_type="auth",
            value=user.model_dump(mode="json"),
            ttl_seconds=settings.auth_user_cache_ttl_seconds,
        )
    return user


async def get_current_user_detached(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    cookie_token: Annotated[Optional[str], Cookie(alias="access_token")] = None,
) -> User:
    """
    Dependency to get the current authenticated user without an open DB session.

    This is suitable for long-running requests (e.g., streaming proxies) where
    holding a DB connection open is undesirable.

    WARNING: The returned User object is DETACHED from any session.
    Accessing lazy-loaded relationships will fail.
    """
    # Reuse authentication logic for token validation and cache
    # First, validate credentials (reusing logic logic from get_current_user conceptually)
    # We duplicate some logic here to avoid the dependency on get_session

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_to_use = token or cookie_token
    if token_to_use is None:
        raise credentials_exception

    try:
        payload = verify_token(token_to_use, "access")
        user_id: str = payload.get("sub")

        # We are doing trict Subject validation
        # Thsis ensure sub is not only a string, but a valid UUID
        # This prevents any potential injection or invalid format issues
        import uuid
        try:
            uuid_obj = uuid.UUID(user_id)
        except (ValueError, TypeError):
            # Log this as a potential security event
            logger.warning(f"Invalid user_id format in token: {user_id}")
            raise credentials_exception

        if not user_id:
             raise credentials_exception

    except Exception:
        # treat all token errors as 401
        raise credentials_exception

    # Check cache
    token_hash = hashlib.sha256(token_to_use.encode("utf-8")).hexdigest()
    cache = _get_user_cache()
    if cache:
        deleted_marker = cache.get(scope_id=user_id, cache_type="deleted")
        if deleted_marker:
            raise credentials_exception
        cached_user = cache.get(scope_id=token_hash, cache_type="auth")
        if cached_user:
            try:
                user = User.model_validate(cached_user)
                if not user.is_active:
                    raise credentials_exception
                return user
            except Exception:
                cache.delete(scope_id=token_hash, cache_type="auth")

    # If not in cache, fetch from DB using a short-lived session context
    from app.core.database import get_session_context

    with get_session_context() as session:
        user = UserService(session).get_user_by_id(user_id)
        if user:
            # Refresh to load immediate attributes (though should be loaded by default)
            session.refresh(user)
            # Expunge from session so it can be used after session closes
            session.expunge(user)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Populate cache
    if cache:
        cache.set(
            scope_id=token_hash,
            cache_type="auth",
            value=user.model_dump(mode="json"),
            ttl_seconds=settings.auth_user_cache_ttl_seconds,
        )

    return user



async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Dependency to verify that the current user is an admin.
    Raises HTTPException with status 403 if user is not an admin.

    Usage:
        @router.get("/admin/users")
        async def list_users(admin: Annotated[User, Depends(get_current_admin_user)]):
            # Only admins can access this endpoint
            ...
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin user attempted to access admin endpoint",
            extra={"user_id": str(current_user.id), "user_email": current_user.email}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


async def get_plus_factory(
    session: Annotated[Session, Depends(get_session)]
):
    """
    Dependency to get PlusFeatureFactory instance.

    Raises:
        HTTPException 403: If license is not found or validation fails
        HTTPException 503: If Plus features are not available in this build
        RuntimeError: If SECRET_KEY environment variable is not set
    """
    try:
        # Import Plus components
        from app.plus import PlusFeatureFactory, PLUS_FEATURES_AVAILABLE
        from app.models.instance_detail import InstanceDetail

        # Check if Plus features are available in this build
        if not PLUS_FEATURES_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "plus_not_available",
                    "message": "Plus features are not available in this build",
                    "upgrade_url": JOURNIV_PLUS_DOC_URL
                }
            )

        # Get instance details from database
        instance = session.query(InstanceDetail).first()

        if not instance:
            logger.error("No instance details found in database")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "no_instance",
                    "message": "Instance not initialized"
                }
            )

        # Check if signed license exists
        if not instance.signed_license:
            logger.info("No Plus license found", extra={"install_id": instance.install_id})
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "license_required",
                    "message": "Journiv Plus license required for this feature",
                    "upgrade_url": JOURNIV_PLUS_DOC_URL
                }
            )

        # Create and return factory
        # Factory generates platform_id internally for hardware change detection
        try:
            factory = PlusFeatureFactory(
                signed_license=instance.signed_license
            )
            return factory

        except PermissionError as e:
            # License verification failed in compiled code
            logger.error(
                "License verification failed in PlusFeatureFactory",
                extra={"error": str(e)}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "license_invalid",
                    "message": "License verification failed",
                    "action": "Please check your license or contact support"
                }
            )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_plus_factory: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while initializing Plus features"
        )
