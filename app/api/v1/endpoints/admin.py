"""
Admin endpoints for user management.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.dependencies import get_current_admin_user, get_session
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError
from app.core.logging_config import log_error, log_user_action
from app.models.user import User
from app.schemas.user import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserUpdate,
    UserResponse,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


def _build_user_response(user: User, user_service: UserService) -> dict:
    """Build user response with timezone and OIDC status."""
    user_dict = user.model_dump()
    user_dict['time_zone'] = user_service.get_user_timezone(user.id)
    user_dict['is_oidc_user'] = user_service.is_oidc_user(str(user.id))
    return user_dict


@router.get(
    "/users",
    response_model=list[AdminUserListResponse],
    responses={
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def list_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """
    List all users (admin only).

    Returns a list of all users with their roles, login type, and linked providers.
    """
    try:
        user_service = UserService(session)
        users = user_service.get_all_users(limit=limit, offset=offset)

        # Build response with additional metadata
        user_list = []
        for user in users:
            # Determine login type from eagerly loaded external_identities
            is_oidc = len(user.external_identities) > 0
            login_type = "oidc" if is_oidc else "local"

            # Get linked OIDC providers
            linked_providers = []
            if is_oidc:
                for ext_id in user.external_identities:
                    linked_providers.append(ext_id.issuer)

            user_list.append(AdminUserListResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role,
                is_active=user.is_active,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                login_type=login_type,
                linked_providers=linked_providers if linked_providers else None
            ))

        log_user_action(admin.email, f"listed {len(user_list)} users")
        return user_list
    except Exception as e:
        log_error(e, user_email=admin.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while listing users"
        ) from e


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Email already registered or invalid data"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def create_user(
    admin: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)],
    user_data: AdminUserCreate
):
    """
    Create a new user as admin (can specify role).

    Admins can create users with any role (admin or user).
    This endpoint bypasses the signup disabled check.
    """
    try:
        user_service = UserService(session)

        # Create new user with specified role
        user = user_service.create_user_as_admin(user_data)

        log_user_action(
            admin.email,
            f"created user {user.email} with role {user.role}"
        )

        user_dict = _build_user_response(user, user_service)
        user_dict['is_oidc_user'] = False

        return UserResponse.model_validate(user_dict)
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log_error(e, user_email=admin.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred during user creation",
        ) from e


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        400: {"description": "Invalid data or cannot update user"},
        403: {"description": "Admin access required"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    }
)
async def update_user(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)],
    user_data: AdminUserUpdate
):
    """
    Update a user as admin (can change role, email, active status).

    Admin protections:
    - Cannot demote the last admin
    - Can promote users to admin
    - Can change email, name, password, active status
    """
    try:
        user_service = UserService(session)

        # Update user
        user = user_service.update_user_as_admin(str(user_id), user_data)

        log_user_action(
            admin.email,
            f"updated user {user.email}"
        )

        user_dict = _build_user_response(user, user_service)

        return UserResponse.model_validate(user_dict)
    except UserNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log_error(e, user_email=admin.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred during user update",
        ) from e


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Cannot delete user (e.g., last admin)"},
        403: {"description": "Admin access required"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    }
)
async def delete_user(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete a user and all their data (admin only).

    Admin protections:
    - Cannot delete the last admin

    All related data (journals, entries, media, tags, mood logs, prompts,
    settings, and writing streaks) are automatically deleted via CASCADE.
    """
    try:
        user_service = UserService(session)

        # Get user to log deletion
        user = user_service.get_user_by_id(str(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_email = user.email

        # Delete user (includes admin protection check)
        user_service.delete_user(str(user_id), bypass_admin_check=False)

        log_user_action(
            admin.email,
            f"deleted user {user_email}"
        )

        return {
            "message": "User deleted successfully",
            "detail": f"User {user_email} and all related data have been permanently deleted"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, user_email=admin.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred during user deletion",
        ) from e
