"""Export and wipe — the user owns every byte."""
from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..deps import get_config, get_db
from ..models import WipeRequest

router = APIRouter(prefix="/api/data")


@router.get("/export")
async def export(request: Request):
    db = get_db(request)
    payload = {
        "settings": db.get_state("settings"),
        "relationship": db.get_state("relationship"),
        "messages": db.query("SELECT * FROM messages ORDER BY id"),
        "facts": db.query("SELECT * FROM facts ORDER BY id"),
        "summaries": db.query("SELECT * FROM summaries ORDER BY id"),
        "photos_generated": db.query("SELECT * FROM photos_generated ORDER BY id"),
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=companion-export.json"})


@router.post("/wipe")
async def wipe(request: Request, body: WipeRequest):
    if body.confirm != "DELETE":
        return JSONResponse({"error": 'confirmation must be exactly "DELETE"'}, status_code=400)
    db = get_db(request)
    config = get_config(request)
    for table in ("messages", "facts", "summaries", "photos_generated", "app_state"):
        db.execute(f"DELETE FROM {table}")
    for d in (config.uploads_dir, config.generated_dir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    return {"ok": True}
