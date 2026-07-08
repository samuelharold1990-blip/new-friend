"""The chat pipeline: SSE streaming replies, selfie handling, uploads, catch-up."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from ..db import now_ms
from ..deps import get_client, get_config, get_db, get_library, get_relationship, load_settings
from ..models import ChatRequest
from ..services import memory, vision
from ..services.catchup import run_catchup
from ..services.photos import SelfieTagFilter, strip_selfie_tags
from ..services.prompt import build_system_prompt, history_messages
from ..services.sd import generate_selfie

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

ALLOWED_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _message_dict(db, message_id: int) -> dict:
    row = db.query_one("SELECT * FROM messages WHERE id = ?", (message_id,))
    if row and row.get("meta"):
        row["meta"] = json.loads(row["meta"])
    return row or {}


@router.get("/messages")
async def get_messages(request: Request, before_id: int | None = None, limit: int = 50):
    db = get_db(request)
    db.set_state("last_seen_at", now_ms())
    return {"messages": db.get_messages(before_id=before_id, limit=min(limit, 200))}


@router.post("/uploads/photo")
async def upload_photo(request: Request, file: UploadFile):
    config = get_config(request)
    ext = Path(file.filename or "photo.jpg").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return JSONResponse({"error": f"unsupported file type {ext}"}, status_code=400)
    upload_id = f"{uuid.uuid4().hex}{ext}"
    dest = config.uploads_dir / upload_id
    dest.write_bytes(await file.read())
    return {"upload_id": upload_id, "path": f"uploads/{upload_id}"}


@router.post("/catchup")
async def catchup(request: Request):
    db = get_db(request)
    settings = load_settings(db)
    ids = await run_catchup(db, settings, get_client(request),
                            get_relationship(request), get_library(request))
    return {"messages": [_message_dict(db, i) for i in ids]}


@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    db = get_db(request)
    config = get_config(request)
    settings = load_settings(db)
    client = get_client(request)
    relationship = get_relationship(request)
    library = get_library(request)

    text = body.text.strip()
    if not text and not body.upload_id:
        return JSONResponse({"error": "empty message"}, status_code=400)

    # incoming photo: validate and (optionally) let a vision model describe it
    photo_path = None
    user_meta: dict = {}
    if body.upload_id:
        upload_file = config.uploads_dir / Path(body.upload_id).name
        if upload_file.exists():
            photo_path = f"uploads/{upload_file.name}"
            desc = await vision.describe_upload(settings, client, upload_file)
            if desc:
                user_meta["vision_description"] = desc

    user_msg_id = db.add_message("user", text, photo_path=photo_path,
                                 photo_kind="user_upload" if photo_path else None,
                                 meta=user_meta or None)
    relationship.add_user_message_points()
    db.set_state("last_seen_at", now_ms())

    state = relationship.get()
    selfies_allowed = relationship.selfies_remaining_today() > 0
    last_row = db.query_one(
        "SELECT created_at FROM messages WHERE id < ? ORDER BY id DESC LIMIT 1", (user_msg_id,))
    system = build_system_prompt(
        db, settings, state["stage"], library, selfies_allowed=selfies_allowed,
        last_message_at=last_row["created_at"] if last_row else None, now_ms_val=now_ms())

    messages = [{"role": "system", "content": system}] + history_messages(db, settings)
    if photo_path and not user_meta.get("vision_description"):
        # no vision model: swap the photo note for a graceful-fallback direction
        user_name = settings.user_name or "they"
        messages[-1]["content"] = f"{text}\n[{user_name} {vision.NO_VISION_NOTE}]".strip()

    async def event_stream():
        tag_filter = SelfieTagFilter()
        full_text = ""
        try:
            async for chunk in client.chat_stream(settings.model, messages):
                full_text += chunk
                safe = tag_filter.feed(chunk)
                if safe:
                    yield _sse("token", {"text": safe})
            tail = tag_filter.flush()
            if tail:
                yield _sse("token", {"text": tail})
        except Exception:
            log.warning("chat stream failed", exc_info=True)
            yield _sse("error", {"message": "Couldn't reach the language model. "
                                            "Check that Ollama is running in Settings."})
            return

        clean, net_mood = strip_selfie_tags(full_text)
        mood = tag_filter.mood or net_mood

        reply_photo_path, reply_photo_kind, reply_meta = None, None, {}
        if mood and selfies_allowed:
            if settings.sd_enabled:
                yield _sse("status", {"state": "taking_photo"})
                reply_photo_path = await generate_selfie(db, settings, mood, config.generated_dir)
                reply_photo_kind = "sd" if reply_photo_path else None
            if not reply_photo_path:
                reply_photo_path = library.pick(mood, state["stage"])
                reply_photo_kind = "pack" if reply_photo_path else None
            if reply_photo_path:
                relationship.record_selfie()
                reply_meta["selfie_mood"] = mood
                yield _sse("photo", {"url": "/" + reply_photo_path, "mood": mood})

        reply_id = db.add_message("companion", clean, photo_path=reply_photo_path,
                                  photo_kind=reply_photo_kind, meta=reply_meta or None)
        yield _sse("done", {"user_message": _message_dict(db, user_msg_id),
                            "reply": _message_dict(db, reply_id)})

        if memory.should_extract(db):
            asyncio.create_task(memory.run_extraction(db, settings, client, relationship))

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
