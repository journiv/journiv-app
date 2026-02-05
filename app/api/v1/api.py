"""
API v1 router.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    analytics,
    auth,
    entries,
    health,
    instance_config,
    journals,
    license,
    location,
    media,
    moods,
    oidc,
    prompts,
    security,
    tags,
    users,
    version,
    weather,
)

# Import/Export routers
from app.api.v1.endpoints.export_data import router as export_router
from app.api.v1.endpoints.import_data import router as import_router
from app.integrations import router as integrations

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(oidc.router)
api_router.include_router(users.router)
api_router.include_router(journals.router)
api_router.include_router(entries.router)
api_router.include_router(moods.router)
api_router.include_router(prompts.router)
api_router.include_router(tags.router)
api_router.include_router(analytics.router)
api_router.include_router(media.router)
api_router.include_router(export_router)
api_router.include_router(import_router)
api_router.include_router(health.router)
api_router.include_router(security.router)
api_router.include_router(version.router)
api_router.include_router(instance_config.router)
api_router.include_router(admin.router)
api_router.include_router(license.router)
api_router.include_router(location.router)
api_router.include_router(weather.router)
api_router.include_router(integrations.router)
