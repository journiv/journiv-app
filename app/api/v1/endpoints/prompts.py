"""
Prompt endpoints.
"""
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import PromptNotFoundError
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.prompt import PromptResponse
from app.services.prompt_service import PromptService

router = APIRouter(prefix="/prompts", tags=["prompts"])


# System Prompts (Protected access)
@router.get(
    "/",
    response_model=List[PromptResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_system_prompts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    category: Optional[str] = Query(None),
    difficulty_level: Optional[int] = Query(None, ge=1, le=5),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Get system prompts with optional filters.

    Supports filtering by category, difficulty level, and pagination.
    """
    prompt_service = PromptService(session)
    try:
        prompts = prompt_service.get_system_prompts(category, difficulty_level, limit)
        return prompts
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving prompts"
        ) from None


@router.get(
    "/random",
    response_model=PromptResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "No prompts available"},
    }
)
async def get_random_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    category: Optional[str] = Query(None),
    difficulty_level: Optional[int] = Query(None, ge=1, le=5)
):
    """
    Get a random system prompt.

    Randomly selects from available system prompts, optionally filtered by category or difficulty.
    """
    prompt_service = PromptService(session)
    try:
        prompt = prompt_service.get_random_prompt(
            user_id=None, category=category, difficulty_level=difficulty_level
        )
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No prompts available"
            )
        return prompt
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving random prompt"
        ) from None


@router.get(
    "/daily",
    responses={
        200: {"description": "Daily prompt available", "model": PromptResponse},
        204: {"description": "No daily prompt available"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_daily_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get a daily prompt for the current user.

    Returns a new prompt each day. Tracks answered prompts to avoid repetition.
    """
    prompt_service = PromptService(session)
    try:
        prompt = prompt_service.get_daily_prompt(current_user.id)
        if not prompt:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return prompt
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving daily prompt"
        ) from None


# Prompt Search and Filtering
@router.get(
    "/search",
    response_model=List[PromptResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def search_prompts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    q: str = Query(..., min_length=1)
):
    """
    Search system prompts by text content.

    Searches both prompt text and categories.
    """
    prompt_service = PromptService(session)
    try:
        prompts = prompt_service.search_prompts(q, user_id=None)
        return prompts
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching prompts"
        ) from None


# Prompt Analytics (must be before /{prompt_id})
@router.get(
    "/analytics/statistics",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_prompt_statistics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get prompt usage statistics for the current user.

    Includes answered prompts count, favorite categories, and completion trends.
    """
    prompt_service = PromptService(session)
    try:
        statistics = prompt_service.get_prompt_statistics(current_user.id)
        return statistics
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving statistics"
        ) from None


@router.get(
    "/{prompt_id}",
    response_model=PromptResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Prompt not found"},
    }
)
async def get_prompt(
    prompt_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific prompt by ID."""
    prompt_service = PromptService(session)
    try:
        prompt = prompt_service.get_prompt_by_id(prompt_id)
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prompt not found"
            )
        return prompt
    except HTTPException:
        raise
    except PromptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found"
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving prompt"
        ) from None
