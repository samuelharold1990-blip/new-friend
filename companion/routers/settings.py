"""Settings, model listing and connection tests."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from ..deps import get_client, get_config, get_db, load_settings, save_settings
from ..models import AppSettings, TestConnectionRequest
from ..services.ollama import MockOllamaClient, OllamaClient
from ..services.sd import auto_connect, check_backend, reference_images

router = APIRouter(prefix="/api")


@router.get("/settings")
async def get_settings(request: Request):
    return load_settings(get_db(request)).model_dump()


@router.put("/settings")
async def put_settings(request: Request, settings: AppSettings):
    db = get_db(request)
    previous = load_settings(db)
    # an explicit off is remembered so auto-connect doesn't fight the user
    if previous.sd_enabled and not settings.sd_enabled:
        db.set_state("sd_user_disabled", True)
    elif settings.sd_enabled:
        db.set_state("sd_user_disabled", False)
    save_settings(db, settings)
    return settings.model_dump()


@router.get("/models")
async def list_models(request: Request):
    client = get_client(request)
    try:
        return {"models": await client.list_models()}
    except Exception:
        return {"models": [], "error": "Could not reach Ollama"}


@router.get("/health")
async def health(request: Request):
    db = get_db(request)
    config = get_config(request)
    settings = load_settings(db)
    client = get_client(request)
    ollama_ok = await client.ping()
    models = []
    if ollama_ok:
        try:
            models = await client.list_models()
        except Exception:
            pass
    settings = await auto_connect(db, settings)  # finds a local SD server by itself
    sd_ok = False
    if settings.sd_enabled:
        sd_ok = await check_backend(settings.sd_backend, settings.sd_url)
    return {
        "ollama": {"reachable": ollama_ok, "models": models},
        "sd": {"enabled": settings.sd_enabled, "reachable": sd_ok,
               "backend": settings.sd_backend, "checkpoint": settings.sd_checkpoint,
               "reference_photos": len(reference_images(config.photos_dir))},
        "vision_available": any(m["is_vision"] for m in models),
        "mock_mode": isinstance(client, MockOllamaClient),
        "onboarding_complete": db.get_state("onboarding_complete", False),
    }


@router.post("/settings/test-connection")
async def test_connection(request: Request, body: TestConnectionRequest):
    if body.kind == "ollama":
        if body.url.startswith("mock"):
            return {"ok": True, "detail": "mock mode"}
        ok = await OllamaClient(body.url).ping()
        return {"ok": ok, "detail": "Ollama reachable" if ok else "No response — is `ollama serve` running?"}
    if body.kind in ("a1111", "comfyui"):
        ok = await check_backend(body.kind, body.url)
        hint = ("running with --api?" if body.kind == "a1111" else "is ComfyUI running?")
        return {"ok": ok, "detail": "Reachable" if ok else f"No response — {hint}"}
    return {"ok": False, "detail": f"unknown kind {body.kind}"}
