"""Seeing the user's photos: a two-step flow.

If a vision model is available it describes the uploaded image, and that
description is injected into the main chat model's context — so the persona
model never changes. Without one, she reacts warmly but generically.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from ..models import AppSettings
from .ollama import is_vision_model

log = logging.getLogger(__name__)

DESCRIBE_PROMPT = ("Describe this photo in 2-3 sentences: what it shows, the setting, "
                   "and the overall mood. Be concrete.")

NO_VISION_NOTE = ("sent a photo. You can't see photos on your current phone, but respond "
                  "warmly, say you wish you could see it properly, and ask about it")


async def describe_upload(settings: AppSettings, client, path: Path) -> str | None:
    """Returns a description string, or None when vision isn't available/fails."""
    if not settings.vision_enabled or not settings.vision_model:
        return None
    try:
        models = [m["name"] for m in await client.list_models()]
        chosen = settings.vision_model
        if chosen not in models:
            match = next((m for m in models if m.split(":")[0] == chosen.split(":")[0]
                          or is_vision_model(m)), None)
            if not match:
                return None
            chosen = match
        image_b64 = base64.b64encode(path.read_bytes()).decode()
        desc = await client.chat_vision(chosen, DESCRIBE_PROMPT, image_b64)
        return desc.strip() or None
    except Exception:
        log.info("vision description failed, using generic reaction", exc_info=True)
        return None
