"""
User endpoints.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_user_action, log_error
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate, UserSettingsResponse, UserSettingsUpdate
from app.services.user_service import UserService

router = APIRouter()


class DeleteResponse(BaseModel):
    """Response schema for delete operations."""
    message: str


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get current authenticated user profile.

    Returns complete user information including account status and timestamps.
    """
    user_service = UserService(session)
    timezone = user_service.get_user_timezone(current_user.id)

    # Check if user is OIDC user using service method
    is_oidc_user = user_service.is_oidc_user(str(current_user.id))

    # Create response with timezone from settings
    user_dict = current_user.model_dump()
    user_dict['time_zone'] = timezone
    user_dict['is_oidc_user'] = is_oidc_user

    return UserResponse.model_validate(user_dict)


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

    Supports updating name, profile picture, and password. Password changes
    require current password verification and will revoke all active sessions.
    """
    # Validate that at least one field is being updated
    if not any([
        user_update.name is not None,
        user_update.profile_picture_url is not None,
        user_update.new_password is not None
    ]):
        log_user_action(current_user.email, "Empty update attempt", request_id="")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    user_service = UserService(session)

    try:
        updated_user = user_service.update_user(str(current_user.id), user_update)
    except ValueError as e:
        # Handle password verification errors
        log_user_action(current_user.email, f"User update failed: {str(e)}", request_id="")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Handle unexpected errors
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user"
        )

    log_user_action(current_user.email, "Updated user", request_id="")

    # Get timezone from settings
    timezone = user_service.get_user_timezone(updated_user.id)

    # Check if user is OIDC user using service method
    is_oidc_user = user_service.is_oidc_user(str(updated_user.id))

    user_dict = updated_user.model_dump()
    user_dict['time_zone'] = timezone
    user_dict['is_oidc_user'] = is_oidc_user

    return UserResponse.model_validate(user_dict)


@router.delete(
    "/me",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Deletion failed"},
    }
)
async def delete_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete current user account.
    """
    user_service = UserService(session)

    try:
        success = user_service.delete_user(str(current_user.id))

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user account"
            )

        log_user_action(current_user.email, "Deleted user", request_id="")

        return DeleteResponse(message="User account deleted successfully")

    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting user account"
        )


@router.get(
    "/me/settings",
    response_model=UserSettingsResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Settings not found"},
    }
)
async def get_current_user_settings(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get current user's settings.

    Returns all user preferences including timezone, notifications, theme, etc.
    """
    user_service = UserService(session)

    try:
        settings = user_service.get_user_settings(str(current_user.id))
        return UserSettingsResponse.model_validate(settings)
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )


@router.put(
    "/me/settings",
    response_model=UserSettingsResponse,
    responses={
        400: {"description": "Invalid data or no fields to update"},
        401: {"description": "Not authenticated"},
        404: {"description": "Settings not found"},
        500: {"description": "Internal server error"},
    }
)
async def update_current_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Update current user's settings.

    Supports updating timezone, theme, notifications, daily goals, etc.
    Frontend should call this after detecting device timezone change.
    """
    user_service = UserService(session)

    try:
        updated_settings = user_service.update_user_settings(str(current_user.id), settings_update)
        log_user_action(current_user.email, "Updated settings", request_id="")
        return UserSettingsResponse.model_validate(updated_settings)
    except ValueError as e:
        log_user_action(current_user.email, f"Settings update failed: {str(e)}", request_id="")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating settings"
        )
