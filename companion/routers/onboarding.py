"""First-run onboarding: connectivity check, model pick, character setup."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..db import now_ms
from ..deps import get_client, get_db, load_settings, save_settings
from ..models import OnboardingRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding")

GREETING_INSTRUCTION = (
    "This is the very first message you ever send {user}. You just exchanged numbers. "
    "Send a short, friendly opening text: say hi, introduce yourself by name, and ask "
    "one easy getting-to-know-you question. 1-2 sentences, casual texting style."
)


@router.get("/status")
async def status(request: Request):
    db = get_db(request)
    client = get_client(request)
    reachable = await client.ping()
    models = []
    if reachable:
        try:
            models = await client.list_models()
        except Exception:
            pass
    return {
        "complete": db.get_state("onboarding_complete", False),
        "ollama_reachable": reachable,
        "ollama_url": load_settings(db).ollama_url,
        "models": models,
    }


@router.post("/complete")
async def complete(request: Request, body: OnboardingRequest):
    db = get_db(request)
    settings = load_settings(db)
    settings.model = body.model
    settings.user_name = body.user_name.strip()
    settings.character = body.character
    save_settings(db, settings)

    # her first text — LLM-written, with a canned fallback so onboarding never fails
    greeting = f"hey {settings.user_name}! it's {settings.character.name} 💛 so happy we're talking. how's your day been?"
    try:
        client = get_client(request)
        system = (f"You are {settings.character.name}. Personality: {settings.character.personality}. "
                  "You text in short casual messages.")
        chunks = []
        async for chunk in client.chat_stream(settings.model, [
                {"role": "system", "content": system},
                {"role": "user", "content": GREETING_INSTRUCTION.format(user=settings.user_name or "them")}]):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        if text:
            greeting = text
    except Exception:
        log.info("greeting generation failed, using canned fallback", exc_info=True)

    message_id = db.add_message("companion", greeting)
    db.set_state("onboarding_complete", True)
    db.set_state("last_seen_at", now_ms())
    return {"ok": True, "greeting_message_id": message_id}
