"""Optional local Stable Diffusion integration (AUTOMATIC1111 or ComfyUI).

When enabled and reachable, selfies are generated live from a prompt built
around the character's appearance with a fixed seed for visual consistency.
Any failure falls back silently to the photo pack.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path

import httpx

from ..db import Database, now_ms
from ..models import AppSettings

log = logging.getLogger(__name__)

GENERATION_TIMEOUT = 90  # seconds end-to-end

MOOD_PROMPTS = {
    "morning": "just woke up, sitting by a bright window, soft morning light, oversized sweater, holding a mug",
    "coffee": "sitting in a cozy cafe holding a coffee mug, warm light, casual sweater, smiling at camera",
    "gym": "in athletic wear after a workout, gym mirror selfie, ponytail, energetic smile",
    "outdoors": "walking outside on a sunny day, casual outfit, candid smile, trees and street in background",
    "selfie_generic": "casual selfie at home, natural expression, everyday clothes",
    "evening": "relaxed evening at home, warm lamp lighting, comfortable clothes, soft smile",
    "cozy": "curled up on a couch under a blanket, fairy lights, holding a book or tea, content expression",
    "dressed_up": "dressed up elegantly for an evening out, tasteful dress, styled hair, warm smile",
}
STYLE_SUFFIX = "amateur smartphone selfie, natural lighting, realistic, high detail, looking at camera"
NEGATIVE_PROMPT = ("nsfw, nude, deformed, bad anatomy, extra fingers, blurry, lowres, "
                   "watermark, text, cartoon, 3d render")
WIDTH, HEIGHT = 768, 1024


def build_prompt(settings: AppSettings, mood: str) -> str:
    mood_part = MOOD_PROMPTS.get(mood, MOOD_PROMPTS["selfie_generic"])
    return f"{settings.character.appearance}, {mood_part}, {STYLE_SUFFIX}"


async def check_backend(kind: str, url: str) -> bool:
    probe = "/sdapi/v1/progress" if kind == "a1111" else "/system_stats"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url.rstrip("/") + probe)
            return r.status_code == 200
    except Exception:
        return False


async def _generate_a1111(url: str, prompt: str, seed: int, out_dir: Path) -> str:
    payload = {
        "prompt": prompt, "negative_prompt": NEGATIVE_PROMPT,
        "seed": seed, "width": WIDTH, "height": HEIGHT, "steps": 25,
        "sampler_name": "DPM++ 2M", "cfg_scale": 6.5,
    }
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
        r = await client.post(url.rstrip("/") + "/sdapi/v1/txt2img", json=payload)
        r.raise_for_status()
        images = r.json().get("images", [])
    if not images:
        raise RuntimeError("A1111 returned no images")
    filename = f"{uuid.uuid4().hex}.png"
    (out_dir / filename).write_bytes(base64.b64decode(images[0]))
    return filename


async def _generate_comfyui(url: str, prompt: str, seed: int, out_dir: Path) -> str:
    workflow_path = Path(__file__).parent / "comfy_workflow.json"
    workflow = workflow_path.read_text()
    workflow = (workflow.replace("{{PROMPT}}", json.dumps(prompt)[1:-1])
                        .replace("{{NEGATIVE}}", json.dumps(NEGATIVE_PROMPT)[1:-1])
                        .replace("{{SEED}}", str(seed))
                        .replace("{{WIDTH}}", str(WIDTH)).replace("{{HEIGHT}}", str(HEIGHT)))
    base = url.rstrip("/")
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
        r = await client.post(f"{base}/prompt", json={"prompt": json.loads(workflow)})
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
        deadline = asyncio.get_event_loop().time() + GENERATION_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(2)
            h = (await client.get(f"{base}/history/{prompt_id}")).json()
            entry = h.get(prompt_id)
            if not entry:
                continue
            for node_output in entry.get("outputs", {}).values():
                for img in node_output.get("images", []):
                    params = {"filename": img["filename"],
                              "subfolder": img.get("subfolder", ""),
                              "type": img.get("type", "output")}
                    img_r = await client.get(f"{base}/view", params=params)
                    img_r.raise_for_status()
                    filename = f"{uuid.uuid4().hex}.png"
                    (out_dir / filename).write_bytes(img_r.content)
                    return filename
        raise TimeoutError("ComfyUI generation timed out")


async def generate_selfie(db: Database, settings: AppSettings, mood: str,
                          out_dir: Path) -> str | None:
    """Returns a 'generated/<file>' path, or None on any failure."""
    if not settings.sd_enabled:
        return None
    prompt = build_prompt(settings, mood)
    try:
        if settings.sd_backend == "comfyui":
            filename = await asyncio.wait_for(
                _generate_comfyui(settings.sd_url, prompt, settings.character_seed, out_dir),
                GENERATION_TIMEOUT)
        else:
            filename = await asyncio.wait_for(
                _generate_a1111(settings.sd_url, prompt, settings.character_seed, out_dir),
                GENERATION_TIMEOUT)
    except Exception:
        log.info("SD generation failed, falling back to photo pack", exc_info=True)
        return None
    db.execute(
        "INSERT INTO photos_generated (filename, mood, prompt, backend, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (filename, mood, prompt, settings.sd_backend, now_ms()))
    return f"generated/{filename}"
