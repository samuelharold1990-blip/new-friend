"""Shared accessors for router handlers (state is attached in main.create_app)."""
from __future__ import annotations

from fastapi import Request

from .config import Config
from .db import Database
from .models import AppSettings
from .services.ollama import make_client
from .services.photos import PhotoLibrary
from .services.relationship import RelationshipEngine


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_library(request: Request) -> PhotoLibrary:
    return request.app.state.library


def get_relationship(request: Request) -> RelationshipEngine:
    return request.app.state.relationship


def load_settings(db: Database) -> AppSettings:
    stored = db.get_state("settings")
    return AppSettings(**stored) if stored else AppSettings()


def save_settings(db: Database, settings: AppSettings) -> None:
    db.set_state("settings", settings.model_dump())


def get_client(request: Request):
    db = get_db(request)
    return make_client(get_config(request), load_settings(db))
