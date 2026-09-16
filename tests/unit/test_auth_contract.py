"""Authentication OpenAPI contract coverage."""

from app.main import app


def test_logout_openapi_is_unauthenticated_with_optional_cookie() -> None:
    operation = app.openapi()["paths"]["/api/v1/auth/logout"]["post"]

    assert operation.get("security") in (None, [])
    assert {
        "name": "access_token",
        "in": "cookie",
        "required": False,
    }.items() <= operation["parameters"][0].items()
    assert set(operation["responses"]) == {"200", "422", "500"}
