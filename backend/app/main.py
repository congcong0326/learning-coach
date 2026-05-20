from fastapi import FastAPI

from backend.app.api.auth import router as auth_router
from backend.app.api.db_health import router as db_health_router
from backend.app.api.health import router as health_router
from backend.app.api.llm_credentials import router as llm_credentials_router
from backend.app.api.problems import router as problems_router
from backend.app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name)
    application.include_router(health_router)
    application.include_router(health_router, prefix=settings.api_prefix)
    application.include_router(auth_router, prefix=settings.api_prefix)
    application.include_router(llm_credentials_router, prefix=settings.api_prefix)
    application.include_router(db_health_router, prefix=settings.api_prefix)
    application.include_router(problems_router, prefix=settings.api_prefix)
    return application


app = create_app()
