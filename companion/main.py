"""FastAPI app factory: wiring, static mounts, startup."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import Config
from .db import Database
from .routers import chat, data, memory, onboarding, photos, settings
from .services.photos import PhotoLibrary
from .services.relationship import RelationshipEngine


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    config.ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.db.close()

    app = FastAPI(title="Companion", lifespan=lifespan)
    app.state.config = config
    app.state.db = Database(config.db_path)
    app.state.library = PhotoLibrary(config.photos_dir, config.generated_dir, app.state.db)
    app.state.relationship = RelationshipEngine(app.state.db)

    for r in (chat, settings, memory, photos, onboarding, data):
        app.include_router(r.router)

    app.mount("/photos", StaticFiles(directory=config.photos_dir), name="photos")
    app.mount("/generated", StaticFiles(directory=config.generated_dir), name="generated")
    app.mount("/uploads", StaticFiles(directory=config.uploads_dir), name="uploads")
    app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="static")
    return app


app = create_app()
