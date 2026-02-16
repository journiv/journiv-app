"""
Moment endpoints.
"""
import uuid
from datetime import date, datetime
from typing import Annotated, Iterable, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from app.api.dependencies import get_current_user, get_session
from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import ValidationError
from app.core.logging_config import log_error, log_warning
from app.models.entry import Entry
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import User
from app.models.user_mood_preference import UserMoodPreference
from app.schemas.activity import ActivityResponse
from app.schemas.entry import EntryPreviewResponse, MomentMediaResponse
from app.schemas.moment import (
    MomentCalendarItem,
    MomentCreate,
    MomentMediaThumbnail,
    MomentMoodActivityResponse,
    MomentPageResponse,
    MomentResponse,
    MomentUpdate,
)
from app.schemas.mood import MoodResponse
from app.services.media_service import MediaService
from app.services.moment_service import MomentNotFoundError, MomentService

router = APIRouter(prefix="/moments", tags=["moments"])

def _require_logged_date(moment: Moment) -> date:
    if moment.logged_date is None:
        raise ValueError("Moment logged_date is missing")
    return moment.logged_date


def _load_mood_preferences(
    session: Session,
    user_id: uuid.UUID,
    mood_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, UserMoodPreference]:
    unique_ids = {mood_id for mood_id in mood_ids if mood_id}
    if not unique_ids:
        return {}
    preferences = session.exec(
        select(UserMoodPreference).where(
            UserMoodPreference.user_id == user_id,
            col(UserMoodPreference.mood_id).in_(normalize_uuid_list(unique_ids)),
        )
    ).all()
    return {preference.mood_id: preference for preference in preferences}


def _build_mood_activity_response(
    link: MomentMoodActivity,
    preferences_map: dict[uuid.UUID, UserMoodPreference],
) -> MomentMoodActivityResponse:
    mood_response = None
    if link.mood:
        mood_response = MoodResponse.model_validate(link.mood)
        preference = preferences_map.get(link.mood_id) if link.mood_id else None
        if preference:
            mood_response.is_hidden = preference.is_hidden
            mood_response.sort_order = preference.sort_order
    return MomentMoodActivityResponse(
        id=link.id,
        mood=mood_response,
        activity=ActivityResponse.model_validate(link.activity) if link.activity else None,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _build_moment_response(
    session: Session,
    moment: Moment,
    current_user: User,
    *,
    media_count: int = 0,
    media: List[MomentMediaThumbnail] | None = None,
) -> MomentResponse:
    entry_preview = None
    if moment.entry_id:
        entry = session.exec(select(Entry).where(Entry.id == moment.entry_id)).first()
        if entry:
            entry_preview = EntryPreviewResponse.model_validate(entry)

    links = session.exec(
        select(MomentMoodActivity)
        .where(MomentMoodActivity.moment_id == moment.id)
        .options(
            selectinload(MomentMoodActivity.mood),  # type: ignore[arg-type]
            selectinload(MomentMoodActivity.activity),  # type: ignore[arg-type]
        )
    ).all()

    preferences_map = _load_mood_preferences(
        session,
        current_user.id,
        [link.mood_id for link in links if link.mood_id],
    )
    mood_activity = [_build_mood_activity_response(link, preferences_map) for link in links]

    logged_date = _require_logged_date(moment)
    return MomentResponse(
        id=moment.id,
        user_id=moment.user_id,
        entry_id=moment.entry_id,
        entry=entry_preview,
        primary_mood_id=moment.primary_mood_id,
        logged_at=moment.logged_at,
        logged_date=logged_date,
        logged_timezone=moment.logged_timezone,
        note=moment.note,
        location_data=moment.location_data,
        weather_data=moment.weather_data,
        mood_activity=mood_activity,
        media_count=media_count,
        media=media or [],
        created_at=moment.created_at,
        updated_at=moment.updated_at,
    )


def _build_moment_responses(
    session: Session,
    moments: List[Moment],
    current_user: User,
    *,
    media_counts: dict[uuid.UUID, int] | None = None,
    media_map: dict[uuid.UUID, List[MomentMediaThumbnail]] | None = None,
) -> List[MomentResponse]:
    if not moments:
        return []

    moment_ids = [moment.id for moment in moments]
    entry_ids = [moment.entry_id for moment in moments if moment.entry_id]

    entry_map: dict[uuid.UUID, EntryPreviewResponse] = {}
    if entry_ids:
        entries = session.exec(select(Entry).where(col(Entry.id).in_(entry_ids))).all()
        entry_map = {entry.id: EntryPreviewResponse.model_validate(entry) for entry in entries}

    links = session.exec(
        select(MomentMoodActivity)
        .where(col(MomentMoodActivity.moment_id).in_(moment_ids))
        .options(
            selectinload(MomentMoodActivity.mood),  # type: ignore[arg-type]
            selectinload(MomentMoodActivity.activity),  # type: ignore[arg-type]
        )
    ).all()

    preferences_map = _load_mood_preferences(
        session,
        current_user.id,
        [link.mood_id for link in links if link.mood_id],
    )

    links_map: dict[uuid.UUID, List[MomentMoodActivityResponse]] = {}
    for link in links:
        links_map.setdefault(link.moment_id, []).append(
            _build_mood_activity_response(link, preferences_map)
        )

    responses: List[MomentResponse] = []
    for moment in moments:
        try:
            logged_date = _require_logged_date(moment)
        except ValueError as exc:
            log_warning(
                exc,
                message="Moment logged_date missing; skipping moment in response",
                moment_id=str(moment.id),
            )
            continue
        responses.append(
            MomentResponse(
                id=moment.id,
                user_id=moment.user_id,
                entry_id=moment.entry_id,
                entry=entry_map.get(moment.entry_id) if moment.entry_id else None,
                primary_mood_id=moment.primary_mood_id,
                logged_at=moment.logged_at,
                logged_date=logged_date,
                logged_timezone=moment.logged_timezone,
                note=moment.note,
                location_data=moment.location_data,
                weather_data=moment.weather_data,
                mood_activity=links_map.get(moment.id, []),
                media_count=(media_counts or {}).get(moment.id, 0),
                media=(media_map or {}).get(moment.id, []),
                created_at=moment.created_at,
                updated_at=moment.updated_at,
            )
        )
    return responses


@router.post(
    "",
    response_model=MomentResponse,
    responses={
        400: {"description": "Invalid moment data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    },
)
async def create_moment(
    moment_data: MomentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    moment_service = MomentService(session)
    try:
        moment = moment_service.create_moment(current_user.id, moment_data)
        return _build_moment_response(session, moment, current_user)
    except (ValueError, ValidationError) as exc:
        log_error(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put(
    "/{moment_id}",
    response_model=MomentResponse,
    responses={
        400: {"description": "Invalid moment data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_moment(
    moment_id: uuid.UUID,
    moment_data: MomentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    moment_service = MomentService(session)
    try:
        moment = moment_service.update_moment(moment_id, current_user.id, moment_data)
        return _build_moment_response(session, moment, current_user)
    except MomentNotFoundError:
        raise HTTPException(status_code=404, detail="Moment not found") from None
    except (ValueError, ValidationError) as exc:
        log_error(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get(
    "",
    response_model=MomentPageResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    },
)
async def get_moments(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor_logged_at: Annotated[datetime | None, Query()] = None,
    cursor_id: Annotated[uuid.UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    include_media: Annotated[str | None, Query()] = None,
    journal_id: Annotated[uuid.UUID | None, Query()] = None,
    mood_ids: List[uuid.UUID] = Query(default_factory=list),  # noqa: B008
    search: Annotated[str | None, Query()] = None,
):
    if (cursor_logged_at is None) ^ (cursor_id is None):
        raise HTTPException(
            status_code=400,
            detail="cursor_logged_at and cursor_id must be provided together",
        )
    if include_media not in (None, "thumbnails"):
        raise HTTPException(status_code=400, detail="include_media must be 'thumbnails' when provided")
    moment_service = MomentService(session)
    moments, next_cursor_logged_at, next_cursor_id = moment_service.get_moments(
        current_user.id,
        limit=limit,
        cursor_logged_at=cursor_logged_at,
        cursor_id=cursor_id,
        start_date=start_date,
        end_date=end_date,
        journal_id=journal_id,
        mood_ids=mood_ids if mood_ids else None,
        search=search,
    )

    media_counts: dict[uuid.UUID, int] = {}
    media_map: dict[uuid.UUID, List[MomentMediaThumbnail]] = {}
    if include_media == "thumbnails" and moments:
        moment_ids = [moment.id for moment in moments]
        media_service = MediaService(session)
        media_counts, media_map = media_service.get_moment_media_thumbnails(
            session,
            current_user.id,
            moment_ids,
        )

    items = _build_moment_responses(
        session,
        moments,
        current_user,
        media_counts=media_counts if include_media == "thumbnails" else None,
        media_map=media_map if include_media == "thumbnails" else None,
    )
    return MomentPageResponse(
        items=items,
        next_cursor_logged_at=next_cursor_logged_at,
        next_cursor_id=next_cursor_id,
    )


@router.get(
    "/calendar",
    response_model=List[MomentCalendarItem],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    },
)
async def get_moment_calendar(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
):
    moment_service = MomentService(session)
    moments = moment_service.get_calendar_summary(current_user.id, start_date, end_date)
    summary: dict[date, MomentCalendarItem] = {}
    for moment in moments:
        try:
            logged_date = _require_logged_date(moment)
        except ValueError as exc:
            log_warning(
                exc,
                message="Moment logged_date missing; skipping moment in calendar response",
                moment_id=str(moment.id),
            )
            continue
        item = summary.get(logged_date)
        if item:
            item.moment_count += 1
            if item.primary_mood_id is None and moment.primary_mood_id is not None:
                item.primary_mood_id = moment.primary_mood_id
        else:
            summary[logged_date] = MomentCalendarItem(
                logged_date=logged_date,
                primary_mood_id=moment.primary_mood_id,
                moment_count=1,
            )
    return list(summary.values())


@router.get(
    "/{moment_id}/media",
    response_model=List[MomentMediaResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    }
)
async def get_moment_media(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get all media attached to a moment."""
    try:
        moment = session.exec(
            select(Moment).where(Moment.id == moment_id, Moment.user_id == current_user.id)
        ).first()
        if not moment:
            raise HTTPException(status_code=404, detail="Moment not found")

        media_service = MediaService(session)
        return media_service.get_signed_moment_media(
            session,
            current_user.id,
            moment_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


