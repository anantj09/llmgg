"""App factory and lifespan wiring. Everything is assembled here, once."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

import app.guards  # noqa: F401 - registers built-in guards
from app import __version__
from app.api import admin, chat, health
from app.config import Settings, get_settings
from app.core.policy import load_policy
from app.observability.logging import configure_logging
from app.observability.store import EventStore
from app.providers.factory import build_provider
from app.services.gateway import GuardrailGateway

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = EventStore(settings.db_path)
        store.init()
        provider = build_provider(settings)
        app.state.gateway = GuardrailGateway(settings, load_policy(settings.policy_path), provider, store)
        yield
        await provider.close()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Policy-driven security proxy for LLM APIs (OpenAI-compatible).",
        lifespan=lifespan,
    )
    # Make request-time dependencies use the same settings object as startup.
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/dashboard")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
