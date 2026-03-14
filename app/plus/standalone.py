"""
Journiv Plus Standalone Service.

A minimal FastAPI application that serves only the Plus routers.
Used when running the Plus module as a privacy-isolated sidecar
(SERVICE_ROLE=plus-service).

Required environment variables:
  DATABASE_URL  — same database as the main backend
  SECRET_KEY    — same JWT signing key as the main backend

Start command (handled by docker-entrypoint.sh):
  uvicorn app.plus.standalone:app --host 0.0.0.0 --port 8001

No migrations are run in this role — schema management is owned by
the main backend (SERVICE_ROLE=app).
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.plus.plus_features import (  # type: ignore[import]
    plus_api_router,
    plus_public_router,
)

docs_enabled = settings.environment != "production"

app = FastAPI(
    title="Journiv Plus Service",
    description="Internal Journiv Plus API sidecar (not for direct public access)",
    version="2.0.0",
    openapi_url="/openapi.json" if docs_enabled else None,
    docs_url="/docs" if docs_enabled else None,
    redoc_url=None,
)

app.include_router(plus_api_router, prefix="/api/v1")
app.include_router(plus_public_router)


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
