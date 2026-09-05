import pytest
from fastapi import HTTPException, status

from app.api.v1.endpoints import prompts
from app.core.exceptions import PromptNotFoundError
from app.models.user import User


@pytest.mark.asyncio
async def test_system_prompt_invalid_category_is_a_client_error(monkeypatch):
    class InvalidCategoryPromptService:
        def __init__(self, _session):
            pass

        def get_system_prompts(self, **_kwargs):
            raise PromptNotFoundError("Invalid prompt category 'not-a-category'")

    monkeypatch.setattr(prompts, "PromptService", InvalidCategoryPromptService)

    with pytest.raises(HTTPException) as exc_info:
        await prompts.get_system_prompts(
            current_user=User(
                email="writer@example.com",
                password="hashed-password",
                name="Writer",
            ),
            session=object(),
            category="not-a-category",
            difficulty_level=None,
            q=None,
            min_minutes=None,
            max_minutes=None,
            limit=50,
            offset=0,
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == "Invalid prompt category 'not-a-category'"
