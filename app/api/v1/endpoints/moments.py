"""
Moment endpoints.
"""
import uuid
from datetime import date, datetime
from typing import Annotated, Iterable, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.api.dependencies import get_current_user, get_session
from app.core.db_utils import normalize_uuid_list
from app.core.exceptions import TagNotFoundError, ValidationError
from app.core.logging_config import log_error, log_warning
from app.integrations.schemas import MomentImmichPeopleSuggestionsResponse
from app.models.enums import GoalLogStatus
from app.models.goal import Goal, GoalLog
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import User
from app.schemas.activity import ActivityResponse
from app.schemas.entry import EntryPreviewResponse, MomentMediaResponse
from app.schemas.moment import (
    MemoriesFilter,
    MomentCalendarItem,
    MomentCompletedGoalResponse,
    MomentCreate,
    MomentMediaThumbnail,
    MomentMemoriesResponse,
    MomentMoodActivityResponse,
    MomentPageResponse,
    MomentResponse,
    MomentUpdate,
    PeopleMatch,
)
from app.schemas.mood import MoodResponse
from app.schemas.person import (
    MomentPeopleReplaceRequest,
    PersonResponse,
    PersonSummaryResponse,
)
from app.schemas.tag import TagResponse
from app.services.immich_face_service import ImmichFaceService
from app.services.media_service import MediaService
from app.services.moment_lookup import MomentNotFoundError
from app.services.moment_service import MomentService
from app.services.person_service import PersonService
from app.services.tag_service import TagService

router = APIRouter(prefix="/moments", tags=["moments"])

def _require_logged_date_tz(moment: Moment) -> date:
    if moment.logged_date_tz is None:
        raise ValueError("Moment logged_date_tz is missing")
    return moment.logged_date_tz


def _build_mood_activity_response(
    link: MomentMoodActivity,
) -> MomentMoodActivityResponse:
    mood_response = None
    if link.mood:
        mood_response = MoodResponse.model_validate(link.mood)
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
    media: List[MomentMediaThumbnail] | None = None,
    completed_goals: List[MomentCompletedGoalResponse] | None = None,
) -> MomentResponse:
    entry_preview = EntryPreviewResponse.model_validate(moment.entry) if moment.entry else None
    links = list(moment.mood_activity_links or [])

    mood_activity = [_build_mood_activity_response(link) for link in links]
    tags = [TagResponse.model_validate(tag) for tag in (moment.tags or []) if tag.user_id == current_user.id]
    people = [
        PersonSummaryResponse(
            id=person.id,
            name=person.name,
            nickname=person.nickname,
            profile_image_url=PersonService.build_profile_image_url(person),
        )
        for person in (moment.people or [])
        if person.user_id == current_user.id and person.archived_at is None
    ]

    logged_date_tz = _require_logged_date_tz(moment)
    return MomentResponse(
        id=moment.id,
        user_id=moment.user_id,
        entry=entry_preview,
        primary_mood_id=moment.primary_mood_id,
        prompt_id=moment.prompt_id,
        logged_at_utc=moment.logged_at_utc,
        logged_date_tz=logged_date_tz,
        logged_timezone=moment.logged_timezone,
        note=moment.note,
        location_json=moment.location_json,
        latitude=moment.latitude,
        longitude=moment.longitude,
        weather_json=moment.weather_json,
        weather_summary=moment.weather_summary,
        is_pinned=moment.is_pinned,
        mood_activity=mood_activity,
        tags=tags,
        people=people,
        completed_goals=completed_goals or [],
        media_count=moment.media_count,
        media=media or [],
        created_at=moment.created_at,
        updated_at=moment.updated_at,
    )


def _load_completed_goals_map(
    session: Session,
    user_id: uuid.UUID,
    moment_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, List[MomentCompletedGoalResponse]]:
    unique_ids = list({moment_id for moment_id in moment_ids if moment_id})
    if not unique_ids:
        return {}
    rows = session.exec(
        select(GoalLog, Goal)
        .join(Goal, col(Goal.id) == col(GoalLog.goal_id))
        .where(
            GoalLog.user_id == user_id,
            col(GoalLog.moment_id).in_(normalize_uuid_list(unique_ids)),
            GoalLog.status == GoalLogStatus.SUCCESS,
        )
        .order_by(col(Goal.position), col(Goal.title))
    ).all()
    results: dict[uuid.UUID, List[MomentCompletedGoalResponse]] = {
        moment_id: [] for moment_id in unique_ids
    }
    for goal_log, goal in rows:
        if goal_log.moment_id is None:
            continue
        results.setdefault(goal_log.moment_id, []).append(
            MomentCompletedGoalResponse(
                goal_id=goal.id,
                title=goal.title,
                icon=goal.icon,
                color_value=goal.color_value,
                status=goal_log.status,
                count=goal_log.count,
            )
        )
    return results


def _build_moment_responses(
    session: Session,
    moments: List[Moment],
    current_user: User,
    *,
    media_map: dict[uuid.UUID, List[MomentMediaThumbnail]] | None = None,
) -> List[MomentResponse]:
    if not moments:
        return []

    links: list[MomentMoodActivity] = []
    for moment in moments:
        links.extend(moment.mood_activity_links or [])

    responses: List[MomentResponse] = []
    completed_goals_map = _load_completed_goals_map(
        session,
        current_user.id,
        [moment.id for moment in moments],
    )
    for moment in moments:
        try:
            logged_date_tz = _require_logged_date_tz(moment)
        except ValueError as exc:
            log_warning(
                exc,
                message="Moment logged_date_tz missing; skipping moment in response",
                moment_id=str(moment.id),
            )
            continue
        responses.append(
            MomentResponse(
                id=moment.id,
                user_id=moment.user_id,
                entry=EntryPreviewResponse.model_validate(moment.entry) if moment.entry else None,
                primary_mood_id=moment.primary_mood_id,
                prompt_id=moment.prompt_id,
                logged_at_utc=moment.logged_at_utc,
                logged_date_tz=logged_date_tz,
                logged_timezone=moment.logged_timezone,
                note=moment.note,
                location_json=moment.location_json,
                latitude=moment.latitude,
                longitude=moment.longitude,
                weather_json=moment.weather_json,
                weather_summary=moment.weather_summary,
                is_pinned=moment.is_pinned,
                mood_activity=[
                    _build_mood_activity_response(link)
                    for link in (moment.mood_activity_links or [])
                ],
                tags=[
                    TagResponse.model_validate(tag)
                    for tag in (moment.tags or [])
                    if tag.user_id == current_user.id
                ],
                people=[
                    PersonSummaryResponse(
                        id=person.id,
                        name=person.name,
                        nickname=person.nickname,
                        profile_image_url=PersonService.build_profile_image_url(person),
                    )
                    for person in (moment.people or [])
                    if person.user_id == current_user.id and person.archived_at is None
                ],
                completed_goals=completed_goals_map.get(moment.id, []),
                media_count=moment.media_count,
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
        return _build_moment_response(
            session,
            moment,
            current_user,
            completed_goals=_load_completed_goals_map(session, current_user.id, [moment.id]).get(moment.id, []),
        )
    except (ValueError, ValidationError) as exc:
        log_error(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


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
    try:
        moments = moment_service.get_calendar_summary(current_user.id, start_date, end_date)
    except Exception as exc:
        log_error(exc, message="Error fetching moment calendar summary", user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    summary: dict[date, MomentCalendarItem] = {}
    for moment in moments:
        try:
            logged_date_tz = _require_logged_date_tz(moment)
        except ValueError as exc:
            log_warning(
                exc,
                message="Moment logged_date_tz missing; skipping moment in calendar response",
                moment_id=str(moment.id),
            )
            continue
        item = summary.get(logged_date_tz)
        if item:
            item.moment_count += 1
            if item.primary_mood_id is None and moment.primary_mood_id is not None:
                item.primary_mood_id = moment.primary_mood_id
        else:
            summary[logged_date_tz] = MomentCalendarItem(
                logged_date_tz=logged_date_tz,
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


@router.get(
    "/{moment_id}/tags",
    response_model=List[TagResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_moment_tags(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    tag_service = TagService(session)
    try:
        return tag_service.get_moment_tags(moment_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post(
    "/{moment_id}/tags",
    response_model=List[TagResponse],
    responses={
        400: {"description": "Invalid tag names or empty list"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def bulk_add_tags_to_moment(
    moment_id: uuid.UUID,
    tag_names: List[str],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if not tag_names:
        raise HTTPException(status_code=400, detail="Tag names list cannot be empty")

    tag_service = TagService(session)
    try:
        return tag_service.bulk_add_tags_to_moment(moment_id, tag_names, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete(
    "/{moment_id}/tags/{tag_id}",
    status_code=204,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment or tag not found"},
        500: {"description": "Internal server error"},
    },
)
async def remove_tag_from_moment(
    moment_id: uuid.UUID,
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    tag_service = TagService(session)
    try:
        tag_service.remove_tag_from_moment(moment_id, tag_id, current_user.id)
    except TagNotFoundError:
        raise HTTPException(status_code=404, detail="Tag not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get(
    "/{moment_id}/people",
    response_model=List[PersonResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_moment_people(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    person_service = PersonService(session)
    try:
        return person_service.get_moment_people(moment_id, current_user.id)
    except MomentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put(
    "/{moment_id}/people",
    response_model=List[PersonResponse],
    responses={
        400: {"description": "Invalid people payload"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def replace_moment_people(
    moment_id: uuid.UUID,
    payload: MomentPeopleReplaceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    person_service = PersonService(session)
    try:
        return person_service.replace_moment_people(
            moment_id=moment_id,
            person_ids=payload.person_ids,
            user_id=current_user.id,
        )
    except MomentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete(
    "/{moment_id}/people/{person_id}",
    status_code=204,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment or person not found"},
        500: {"description": "Internal server error"},
    },
)
async def remove_person_from_moment(
    moment_id: uuid.UUID,
    person_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    person_service = PersonService(session)
    try:
        person_service.remove_person_from_moment(
            moment_id=moment_id,
            person_id=person_id,
            user_id=current_user.id,
        )
    except MomentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post(
    "/{moment_id}/people/suggestions/immich",
    response_model=MomentImmichPeopleSuggestionsResponse,
    responses={
        400: {"description": "Immich integration not connected or invalid request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_immich_people_suggestions(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = ImmichFaceService(session)
    try:
        return await service.get_moment_suggestions(current_user.id, moment_id)
    except ValueError as exc:
        message = str(exc)
        if message == "Moment not found":
            raise HTTPException(status_code=404, detail=message) from None
        raise HTTPException(status_code=400, detail=message) from None
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get(
    "/memories",
    response_model=MomentMemoriesResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    },
)
async def get_memories(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    memories_filter: Annotated[MemoriesFilter | None, Query(alias="filter")] = None,
    include_media: Annotated[str | None, Query()] = "thumbnails",
):
    requested_filter = memories_filter or MemoriesFilter.auto
    if include_media not in (None, "thumbnails"):
        raise HTTPException(status_code=400, detail="include_media must be 'thumbnails' when provided")
    moment_service = MomentService(session)
    try:
        moments, applied_filter = moment_service.get_memories(
            current_user.id,
            limit=limit,
            memories_filter=requested_filter,
        )
    except Exception as exc:
        log_error(exc, message="Error fetching memories", user_id=str(current_user.id))
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    media_map: dict[uuid.UUID, List[MomentMediaThumbnail]] = {}
    if include_media == "thumbnails" and moments:
        moment_ids = [moment.id for moment in moments]
        media_service = MediaService(session)
        _, media_map = media_service.get_moment_media_thumbnails(
            session,
            current_user.id,
            moment_ids,
        )
    items = _build_moment_responses(
        session,
        moments,
        current_user,
        media_map=media_map if include_media == "thumbnails" else None,
    )
    return MomentMemoriesResponse(
        items=items,
        requested_filter=requested_filter,
        applied_filter=applied_filter,
    )


@router.get(
    "/{moment_id}",
    response_model=MomentResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_moment(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    moment_service = MomentService(session)
    try:
        moment = moment_service.get_moment(current_user.id, moment_id)
        # For single moment retrieval, include media thumbnails.
        media_service = MediaService(session)
        _, media_map = media_service.get_moment_media_thumbnails(
            session,
            current_user.id,
            [moment.id],
        )

        return _build_moment_response(
            session,
            moment,
            current_user,
            media=media_map.get(moment.id, []),
            completed_goals=_load_completed_goals_map(session, current_user.id, [moment.id]).get(moment.id, []),
        )
    except MomentNotFoundError:
        raise HTTPException(status_code=404, detail="Moment not found") from None
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
        return _build_moment_response(
            session,
            moment,
            current_user,
            completed_goals=_load_completed_goals_map(session, current_user.id, [moment.id]).get(moment.id, []),
        )
    except MomentNotFoundError:
        raise HTTPException(status_code=404, detail="Moment not found") from None
    except (ValueError, ValidationError) as exc:
        log_error(exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete(
    "/{moment_id}",
    status_code=204,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Moment not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_moment(
    moment_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    moment_service = MomentService(session)
    try:
        moment_service.delete_moment(moment_id, current_user.id)
    except MomentNotFoundError:
        raise HTTPException(status_code=404, detail="Moment not found") from None
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
    cursor_logged_at_utc: Annotated[datetime | None, Query()] = None,
    cursor_id: Annotated[uuid.UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    include_media: Annotated[str | None, Query()] = None,
    journal_id: Annotated[uuid.UUID | None, Query()] = None,
    mood_ids: List[uuid.UUID] = Query(default_factory=list),  # noqa: B008
    person_ids: List[uuid.UUID] = Query(default_factory=list),  # noqa: B008
    people_match: Annotated[PeopleMatch | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    include_drafts: Annotated[bool, Query()] = False,
    include_empty: Annotated[bool, Query()] = False,
):
    if (cursor_logged_at_utc is None) ^ (cursor_id is None):
        raise HTTPException(
            status_code=400,
            detail="cursor_logged_at_utc and cursor_id must be provided together",
        )
    if include_media not in (None, "thumbnails"):
        raise HTTPException(status_code=400, detail="include_media must be 'thumbnails' when provided")
    moment_service = MomentService(session)
    moments, next_cursor_logged_at_utc, next_cursor_id = moment_service.get_moments(
        current_user.id,
        limit=limit,
        cursor_logged_at_utc=cursor_logged_at_utc,
        cursor_id=cursor_id,
        start_date=start_date,
        end_date=end_date,
        journal_id=journal_id,
        mood_ids=mood_ids if mood_ids else None,
        person_ids=person_ids if person_ids else None,
        people_match=people_match or PeopleMatch.any,
        search=search,
        include_drafts=include_drafts,
        include_empty=include_empty,
    )

    media_map: dict[uuid.UUID, List[MomentMediaThumbnail]] = {}
    if include_media == "thumbnails" and moments:
        moment_ids = [moment.id for moment in moments]
        media_service = MediaService(session)
        _, media_map = media_service.get_moment_media_thumbnails(
            session,
            current_user.id,
            moment_ids,
        )

    items = _build_moment_responses(
        session,
        moments,
        current_user,
        media_map=media_map if include_media == "thumbnails" else None,
    )
    return MomentPageResponse(
        items=items,
        next_cursor_logged_at_utc=next_cursor_logged_at_utc,
        next_cursor_id=next_cursor_id,
    )
