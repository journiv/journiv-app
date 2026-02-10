"""
Analytics endpoints.
"""
import logging
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.user import User
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])



# Writing Streak Analytics
@router.get(
    "/writing-streak",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_writing_streak(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get writing streak analytics.

    Returns current streak, longest streak, and total entries written.
    """
    try:
        analytics_service = AnalyticsService(session)
        analytics = analytics_service.get_writing_analytics(current_user.id)
        return analytics
    except Exception as e:
        logger.error(
            "Unexpected error fetching writing streak",
            extra={"user_id": str(current_user.id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching writing streak") from None




# Writing Patterns
@router.get(
    "/writing-patterns",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_writing_patterns(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365)
):
    """
    Get writing patterns over time.

    Analyzes writing frequency, peak times, and trends for the specified period.
    """
    try:
        analytics_service = AnalyticsService(session)
        patterns = analytics_service.get_writing_patterns(current_user.id, days)
        return patterns
    except Exception as e:
        logger.error(
            "Unexpected error fetching writing patterns",
            extra={"user_id": str(current_user.id), "days": days, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching writing patterns") from None


# Productivity Metrics
@router.get(
    "/productivity",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_productivity_metrics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get productivity metrics.

    Returns entries per day, words per entry, and consistency scores.
    """
    try:
        analytics_service = AnalyticsService(session)
        metrics = analytics_service.get_productivity_metrics(current_user.id)
        return metrics
    except Exception as e:
        logger.error(
            "Unexpected error fetching productivity metrics",
            extra={"user_id": str(current_user.id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching productivity metrics") from None


# Journal Analytics
@router.get(
    "/journals",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_journal_analytics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get analytics for all journals.

    Returns entry counts, activity breakdown, and statistics per journal.
    """
    try:
        analytics_service = AnalyticsService(session)
        analytics = analytics_service.get_journal_analytics(current_user.id)
        return analytics
    except Exception as e:
        logger.error(
            "Unexpected error fetching journal analytics",
            extra={"user_id": str(current_user.id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching journal analytics") from None


# Comprehensive Dashboard
@router.get(
    "/dashboard",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_analytics_dashboard(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365)
):
    """
    Get comprehensive analytics dashboard.

    Combines all analytics data into a single response with summary statistics.
    """
    try:
        analytics_service = AnalyticsService(session)

        # Get all analytics data
        writing_analytics = analytics_service.get_writing_analytics(current_user.id)
        writing_patterns = analytics_service.get_writing_patterns(current_user.id, days)
        productivity_metrics = analytics_service.get_productivity_metrics(current_user.id)
        journal_analytics = analytics_service.get_journal_analytics(current_user.id)

        result = {
            "writing_streak": writing_analytics,
            "writing_patterns": writing_patterns,
            "productivity": productivity_metrics,
            "journals": journal_analytics,
            "summary": {
                "total_journals": len(journal_analytics.get("journals", [])),
                "total_entries": writing_analytics.get("total_entries", 0),
                "current_streak": writing_analytics.get("current_streak", 0),
                "longest_streak": writing_analytics.get("longest_streak", 0)
            }
        }
        return result
    except Exception as e:
        logger.error(
            "Unexpected error fetching analytics dashboard",
            extra={"user_id": str(current_user.id), "days": days, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching analytics dashboard") from None

