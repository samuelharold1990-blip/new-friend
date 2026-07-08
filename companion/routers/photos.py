"""Photo manifest preview and SD test generation (settings screen)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps import get_config, get_db, get_library, load_settings
from ..models import GeneratePhotoRequest
from ..services.sd import generate_selfie

router = APIRouter(prefix="/api/photos")


@router.get("/manifest")
async def manifest(request: Request):
    return get_library(request).manifest()


@router.post("/generate")
async def generate(request: Request, body: GeneratePhotoRequest):
    db = get_db(request)
    settings = load_settings(db)
    if not settings.sd_enabled:
        return JSONResponse({"error": "Stable Diffusion is not enabled in settings"},
                            status_code=400)
    config = get_config(request)
    path = await generate_selfie(db, settings, body.mood, config.generated_dir, config.photos_dir)
    if not path:
        return JSONResponse({"error": "Generation failed — check the SD server and its logs"},
                            status_code=502)
    return {"url": "/" + path, "mood": body.mood}
