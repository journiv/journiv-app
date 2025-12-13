"""
Authentication endpoints.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import InvalidCredentialsError, UnauthorizedError
from app.core.logging_config import log_user_action, log_error, log_warning
from app.core.rate_limiting import auth_rate_limit
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.models.user import User
from app.schemas.auth import Token, LoginResponse, UserLogin, TokenRefresh
from app.schemas.user import UserResponse, UserCreate
from app.services.user_service import UserService

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Email already registered or invalid data"},
        429: {"description": "Too many requests"},
        500: {"description": "Internal server error"},
        403: {"description": "Sign up is disabled"},
    }
)
@auth_rate_limit("register")
async def register(
    request: Request,
    user_data: UserCreate,
    session: Annotated[Session, Depends(get_session)]
):
    """
    Register a new user account.

    Creates a new user with email and password. Email must be unique.
    """
    try:
        user_service = UserService(session)

        # Check if this is the first user (bootstrap override)
        is_first = user_service.is_first_user()

        # Block signup if disabled (unless this is the first user)
        if not is_first and user_service.is_signup_disabled():
            log_warning(
                "Email signup rejected because signup is disabled",
                user_email=user_data.email
            )
            raise HTTPException(status_code=403, detail="Sign up is disabled")

        # Check if user already exists
        existing_user = user_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create new user (first user becomes admin automatically)
        user = user_service.create_user(user_data)
        log_user_action(user.email, "registered", request_id=getattr(request.state, 'request_id', None))

        # Get timezone from settings
        timezone = user_service.get_user_timezone(user.id)

        # Password-registered users are never OIDC users
        user_dict = user.model_dump(mode='json')
        user_dict['time_zone'] = timezone
        user_dict['is_oidc_user'] = False

        return UserResponse.model_validate(user_dict)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_error(e, request_id=getattr(request.state, 'request_id', None), user_email=user_data.email)
        raise HTTPException(status_code=500, detail="An error occurred during registration")


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"description": "Incorrect email or password"},
        429: {"description": "Too many requests"},
        500: {"description": "Internal server error"},
    }
)
@auth_rate_limit("login")
async def login(
    request: Request,
    response: Response,
    user_data: UserLogin,
    session: Annotated[Session, Depends(get_session)]
):
    """
    Login with email and password.

    Returns access token, refresh token, and user information.
    """
    try:
        user_service = UserService(session)

        # Authenticate user
        try:
            user = user_service.authenticate_user(user_data.email, user_data.password)
        except InvalidCredentialsError:
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except UnauthorizedError:
            raise HTTPException(
                status_code=401,
                detail="User account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        # Create tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # Set secure HttpOnly cookie for web video streaming
        # TODO: WIP.
        # response.set_cookie(
        #     key="access_token",
        #     value=access_token,
        #     httponly=True,
        #     secure=True,  # Set to True in production (requires HTTPS)
        #     samesite="strict",
        #     max_age=settings.access_token_expire_minutes * 60  # Convert minutes to seconds
        # )

        # Get timezone from settings
        timezone = user_service.get_user_timezone(user.id)

        # Convert user to dict for response
        # Use the enum value (e.g., "user" or "admin") instead of str() which gives "UserRole.USER"
        role_value = user.role.value if hasattr(user.role, 'value') else user.role

        user_dict = {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": role_value,  # Include role field
            "is_active": user.is_active,
            "time_zone": timezone,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None
        }

        log_user_action(user.email, "logged in", request_id=getattr(request.state, 'request_id', None))
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_dict
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=getattr(request.state, 'request_id', None), user_email=user_data.email)
        raise HTTPException(status_code=500, detail="An error occurred during login")


@router.post(
    "/refresh",
    response_model=Token,
    responses={
        401: {"description": "Invalid or expired refresh token"},
        500: {"description": "Internal server error"},
    }
)
async def refresh_token(
    token_data: TokenRefresh,
    session: Annotated[Session, Depends(get_session)]
):
    """
    Refresh access token using refresh token.

    Returns a new access token only. The refresh token is NOT rotated - client should continue
    using the same refresh token until it expires. This ensures
    users must re-login periodically, improving security for self-hosted deployments.

    The client should:
    1. Keep using the same refresh token
    2. Use the new access token for API requests
    3. Re-login when the refresh token expires
    """
    try:
        # Verify refresh token
        payload = verify_token(token_data.refresh_token, "refresh")
        user_id = payload.get("sub")

        # Validate claim type
        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user
        user_service = UserService(session)
        user = user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create new access token only (do not rotate refresh token)
        access_token = create_access_token(data={"sub": str(user.id)})

        log_user_action(user.email, "refreshed access token", request_id=None)
        return Token(
            access_token=access_token,
            token_type="bearer"
            # refresh_token is intentionally omitted - client keeps using the same one
        )

    except HTTPException:
        raise
    except JWTError as e:
        log_error(e, request_id=None)
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        log_error(e, request_id=None)
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/token",
    response_model=Token,
    responses={
        401: {"description": "Incorrect email or password"},
        429: {"description": "Too many requests"},
        500: {"description": "Internal server error"},
    }
)
@auth_rate_limit("login")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)]
):
    """
    OAuth2 compatible login endpoint for Swagger UI.

    Use email in username field. Returns access and refresh tokens.
    """
    try:
        user_service = UserService(session)

        # Authenticate user (OAuth2 uses 'username' field for email)
        try:
            user = user_service.authenticate_user(form_data.username, form_data.password)
        except InvalidCredentialsError:
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except UnauthorizedError:
            raise HTTPException(
                status_code=401,
                detail="User account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        # Create tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # # Set secure HttpOnly cookie for web video streaming
        # TODO: WIP.
        # response.set_cookie(
        #     key="access_token",
        #     value=access_token,
        #     httponly=True,
        #     secure=True,  # Set to True in production (requires HTTPS)
        #     samesite="strict",
        #     max_age=settings.access_token_expire_minutes * 60  # Convert minutes to seconds
        # )

        log_user_action(user.email, "logged in via OAuth2", request_id=None)
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=form_data.username)
        raise HTTPException(status_code=500, detail="An error occurred during login")


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    }
)
async def logout(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Logout user. Tokens are stateless and don't need revocation.

    Client should discard both access and refresh tokens after logout.
    """
    try:
        # Simple logout - just log the action
        # In the current implementation, tokens are stateless and don't need revocation
        # TODO: Implement token revocation in future versions.
        log_user_action(current_user.email, "logged out", request_id=None)
        return {
            "message": "Successfully logged out",
            "detail": "Your session has been terminated"
        }
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred during logout")
