from datetime import UTC, date, datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app import models as _models  # noqa: F401
from app.models.base import BaseModel
from app.models.moment import Moment
from app.models.prompt import Prompt
from app.models.user import User
from app.services.prompt_service import PromptService
from app.services.user_service import UserService


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _prompt(
    *,
    text: str,
    category: str,
    difficulty_level: int,
    created_at: datetime,
    estimated_time_minutes: int = 5,
    is_active: bool = True,
) -> Prompt:
    return Prompt(
        text=text,
        category=category,
        difficulty_level=difficulty_level,
        estimated_time_minutes=estimated_time_minutes,
        is_active=is_active,
        created_at=created_at,
        updated_at=created_at,
    )


def test_system_prompt_pages_and_filter_counts_are_deterministic():
    PromptService.invalidate_cache()
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add_all(
            [
                _prompt(
                    text="Newest gratitude",
                    category="gratitude",
                    difficulty_level=1,
                    created_at=now,
                ),
                _prompt(
                    text="Reflection prompt",
                    category="reflection",
                    difficulty_level=2,
                    created_at=now - timedelta(minutes=1),
                ),
                _prompt(
                    text="Older gratitude",
                    category="gratitude",
                    difficulty_level=1,
                    created_at=now - timedelta(minutes=2),
                ),
                _prompt(
                    text="Inactive prompt",
                    category="gratitude",
                    difficulty_level=1,
                    created_at=now - timedelta(minutes=3),
                    is_active=False,
                ),
            ]
        )
        session.commit()

        service = PromptService(session)
        first_page = service.get_system_prompts(limit=1, offset=0)
        second_page = service.get_system_prompts(limit=1, offset=1)

        assert [prompt.text for prompt in first_page] == ["Newest gratitude"]
        assert [prompt.text for prompt in second_page] == ["Reflection prompt"]
        assert service.count_system_prompts() == 3
        assert service.count_system_prompts(category="gratitude") == 2
        assert service.count_system_prompts_by_category() == {
            "gratitude": 2,
            "reflection": 1,
        }
        assert service.count_system_prompts_by_category(difficulty_level=1) == {
            "gratitude": 2,
        }


def test_system_prompt_browse_filters_search_duration_and_category_counts():
    PromptService.invalidate_cache()
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add_all(
            [
                _prompt(
                    text="A gratitude reflection",
                    category="gratitude",
                    difficulty_level=1,
                    estimated_time_minutes=5,
                    created_at=now,
                ),
                _prompt(
                    text="A deeper gratitude reflection",
                    category="gratitude",
                    difficulty_level=2,
                    estimated_time_minutes=15,
                    created_at=now - timedelta(minutes=1),
                ),
                _prompt(
                    text="A reflection on your day",
                    category="reflection",
                    difficulty_level=2,
                    estimated_time_minutes=15,
                    created_at=now - timedelta(minutes=2),
                ),
                _prompt(
                    text="Discover yourself",
                    category="self_discovery",
                    difficulty_level=2,
                    estimated_time_minutes=20,
                    created_at=now - timedelta(minutes=3),
                ),
            ]
        )
        session.commit()

        service = PromptService(session)
        matching = service.get_system_prompts(
            q="reflection", min_minutes=10, max_minutes=15
        )

        assert [prompt.text for prompt in matching] == [
            "A deeper gratitude reflection",
            "A reflection on your day",
        ]
        assert (
            service.count_system_prompts(q="reflection", min_minutes=10, max_minutes=15)
            == 2
        )
        assert (
            service.count_system_prompts(
                category="gratitude", q="reflection", min_minutes=10, max_minutes=15
            )
            == 1
        )
        # Filter chips remain useful after selecting a category: these counts
        # describe the query, but intentionally exclude the active category.
        assert service.count_system_prompts_by_category(
            q="reflection", min_minutes=10, max_minutes=15
        ) == {"gratitude": 1, "reflection": 1}
        assert [
            prompt.text for prompt in service.get_system_prompts(q="self discovery")
        ] == ["Discover yourself"]
        assert [
            prompt.text for prompt in service.get_system_prompts(q="self-discovery")
        ] == ["Discover yourself"]


def test_prompt_responses_count_only_the_current_writers_moments(monkeypatch):
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    # Keep the fixture's September 1–2 answers historical for the writer.
    # 06:00 UTC is still September 4 in Los Angeles.
    now = datetime(2026, 9, 5, 6, tzinfo=UTC)
    monkeypatch.setattr("app.services.prompt_service.utc_now", lambda: now)
    monkeypatch.setattr(
        UserService, "get_user_timezone", lambda _self, _user_id: "America/Los_Angeles"
    )

    with Session(engine) as session:
        writer = User(
            email="writer@example.com",
            password="hashed-password",
            name="Writer",
        )
        another_writer = User(
            email="another@example.com",
            password="hashed-password",
            name="Another writer",
        )
        first_prompt = _prompt(
            text="First prompt",
            category="gratitude",
            difficulty_level=1,
            created_at=now,
        )
        second_prompt = _prompt(
            text="Second prompt",
            category="reflection",
            difficulty_level=2,
            created_at=now,
        )
        session.add_all([writer, another_writer, first_prompt, second_prompt])
        session.commit()

        session.add_all(
            [
                Moment(
                    user_id=writer.id,
                    prompt_id=first_prompt.id,
                    logged_date_tz=date(2026, 9, 1),
                ),
                Moment(
                    user_id=writer.id,
                    prompt_id=first_prompt.id,
                    logged_date_tz=date(2026, 9, 1),
                ),
                Moment(
                    user_id=writer.id,
                    prompt_id=second_prompt.id,
                    logged_date_tz=date(2026, 9, 2),
                ),
                Moment(user_id=another_writer.id, prompt_id=first_prompt.id),
            ]
        )
        session.commit()

        service = PromptService(session)
        responses = service.prompt_responses([first_prompt, second_prompt], writer.id)

        assert [response.answered_count for response in responses] == [2, 1]
        assert (
            service.prompt_response(first_prompt, another_writer.id).answered_count == 1
        )

        statistics = service.get_prompt_statistics(writer.id)
        assert statistics["prompts_answered"] == 2
        assert statistics["total_answers"] == 3
        # The dates are historical, so they contribute to the trend but not a
        # streak the writer is currently maintaining.
        assert statistics["current_streak"] == 0
        assert statistics["favorite_categories"] == [
            {"category": "gratitude", "answered_count": 2},
            {"category": "reflection", "answered_count": 1},
        ]
        assert statistics["completion_trend"] == [
            {"week_start": date(2026, 8, 31), "answered_count": 3},
        ]
        assert statistics["most_used_prompt"]["id"] == first_prompt.id
        assert statistics["most_used_prompt"]["answered_count"] == 2


def test_prompt_statistics_streak_uses_the_writers_local_today(monkeypatch):
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    now = datetime(2026, 9, 4, 6, tzinfo=UTC)
    # 06:00 UTC is still 2026-09-03 in Los Angeles.
    monkeypatch.setattr("app.services.prompt_service.utc_now", lambda: now)
    monkeypatch.setattr(
        UserService, "get_user_timezone", lambda _self, _user_id: "America/Los_Angeles"
    )

    with Session(engine) as session:
        writer = User(
            email="writer@example.com",
            password="hashed-password",
            name="Writer",
        )
        prompt = _prompt(
            text="A prompt",
            category="gratitude",
            difficulty_level=1,
            created_at=now,
        )
        session.add_all([writer, prompt])
        session.commit()
        session.add_all(
            [
                Moment(
                    user_id=writer.id,
                    prompt_id=prompt.id,
                    logged_date_tz=date(2026, 9, 2),
                ),
                Moment(
                    user_id=writer.id,
                    prompt_id=prompt.id,
                    logged_date_tz=date(2026, 9, 1),
                ),
            ]
        )
        session.commit()

        # Yesterday is a live streak; the older consecutive date extends it.
        statistics = PromptService(session).get_prompt_statistics(writer.id)
        assert statistics["current_streak"] == 2
