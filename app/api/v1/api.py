"""
API v1 router.
"""
from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, journals, entries, moods, prompts, tags, analytics, media, health, security, oidc

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(oidc.router, tags=["authentication"])  # OIDC routes (prefix already in router)
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(journals.router, prefix="/journals", tags=["journals"])
api_router.include_router(entries.router, prefix="/entries", tags=["entries"])
api_router.include_router(moods.router, prefix="/moods", tags=["moods"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
