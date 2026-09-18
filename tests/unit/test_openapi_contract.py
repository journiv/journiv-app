"""OpenAPI contract guards that need no running server."""


def test_logout_publishes_no_cookie_parameter():
    """`/auth/logout` must not document an `access_token` cookie parameter.

    The schema is the observable half of the dead-cookie-fallback rule in
    frontend/docs/known-gaps.md: a cookie parameter reaching the spec means
    the fallback was wired up again, and it would also reach the committed
    frontend/openapi/openapi.json and the generated TypeScript client.
    """
    from app.main import app

    operation = app.openapi()["paths"]["/api/v1/auth/logout"]["post"]
    cookie_parameters = [
        parameter
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "cookie"
    ]
    assert cookie_parameters == []
