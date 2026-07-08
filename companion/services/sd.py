"""Local Stable Diffusion integration — zero-config.

The app connects itself: it probes the standard local ports for AUTOMATIC1111
(:7860) and ComfyUI (:8188), enables generation when one responds, picks a
good installed checkpoint automatically (preferring photoreal models), applies
Pony-family score tags when the checkpoint needs them, and — when reference
photos of her exist in photos/reference/ — switches to an IPAdapter FaceID
workflow (ComfyUI) so her face stays consistent across every selfie.

Any failure at any point falls back silently to the photo pack.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from pathlib import Path

import httpx

from ..db import Database, now_ms
from ..models import AppSettings

log = logging.getLogger(__name__)

GENERATION_TIMEOUT = 120  # seconds end-to-end
AUTODETECT_CANDIDATES = [
    ("a1111", "http://localhost:7860"),
    ("comfyui", "http://localhost:8188"),
]
# preference order when picking a checkpoint automatically
CHECKPOINT_PREFERENCE = ("cyberrealistic", "realvis", "juggernaut", "realistic",
                         "photon", "pony", "xl")
PONY_HINT = re.compile(r"pony|score_9", re.I)
REFERENCE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

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
PONY_PREFIX = "score_9, score_8_up, score_7_up, realistic, photo"
PONY_NEGATIVE_EXTRA = ", score_4, score_3, source_anime, source_cartoon, source_furry"
WIDTH, HEIGHT = 768, 1024

WORKFLOW_DIR = Path(__file__).parent


def is_pony_checkpoint(name: str) -> bool:
    return bool(PONY_HINT.search(name or ""))


def build_prompt(settings: AppSettings, mood: str) -> str:
    mood_part = MOOD_PROMPTS.get(mood, MOOD_PROMPTS["selfie_generic"])
    parts = []
    prefix = settings.sd_prompt_prefix.strip()
    if not prefix and is_pony_checkpoint(settings.sd_checkpoint):
        prefix = PONY_PREFIX
    if prefix:
        parts.append(prefix)
    parts += [settings.character.appearance, mood_part, STYLE_SUFFIX]
    return ", ".join(p for p in parts if p)


def build_negative(settings: AppSettings) -> str:
    neg = NEGATIVE_PROMPT
    if is_pony_checkpoint(settings.sd_checkpoint) or "score_9" in settings.sd_prompt_prefix:
        neg += PONY_NEGATIVE_EXTRA
    return neg


def reference_images(photos_dir: Path) -> list[Path]:
    ref_dir = photos_dir / "reference"
    if not ref_dir.is_dir():
        return []
    return sorted(f for f in ref_dir.iterdir() if f.suffix.lower() in REFERENCE_EXTS)


async def check_backend(kind: str, url: str) -> bool:
    probe = "/sdapi/v1/progress" if kind == "a1111" else "/system_stats"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url.rstrip("/") + probe)
            return r.status_code == 200
    except Exception:
        return False


async def autodetect() -> tuple[str, str] | None:
    """Probe the standard local ports; returns (backend, url) or None."""
    for kind, url in AUTODETECT_CANDIDATES:
        if await check_backend(kind, url):
            return kind, url
    return None


async def list_checkpoints(kind: str, url: str) -> list[str]:
    base = url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if kind == "a1111":
                r = await client.get(f"{base}/sdapi/v1/sd-models")
                r.raise_for_status()
                return [m["title"].split(" [")[0] for m in r.json()]
            r = await client.get(f"{base}/object_info/CheckpointLoaderSimple")
            r.raise_for_status()
            info = r.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            return list(info)
    except Exception:
        log.info("could not list SD checkpoints", exc_info=True)
        return []


def pick_checkpoint(available: list[str], preferred: str = "") -> str:
    """The configured checkpoint if installed, else the best-looking photoreal one."""
    if not available:
        return preferred
    if preferred:
        for name in available:
            if preferred.lower() in name.lower():
                return name
    for hint in CHECKPOINT_PREFERENCE:
        for name in available:
            if hint in name.lower():
                return name
    return available[0]


async def auto_connect(db: Database, settings: AppSettings) -> AppSettings:
    """Called on health checks: find a local SD server and wire it up.

    Respects the user: only flips sd_enabled on when it was never explicitly
    configured, and never overrides a checkpoint the user chose.
    """
    if settings.sd_enabled:
        # already on — just make sure a checkpoint is resolved
        if not settings.sd_checkpoint:
            available = await list_checkpoints(settings.sd_backend, settings.sd_url)
            if available:
                settings.sd_checkpoint = pick_checkpoint(available)
                _save(db, settings)
        return settings
    if db.get_state("sd_user_disabled", False):
        return settings

    found = await autodetect()
    if not found:
        return settings
    kind, url = found
    settings.sd_backend, settings.sd_url, settings.sd_enabled = kind, url, True
    available = await list_checkpoints(kind, url)
    if available:
        settings.sd_checkpoint = pick_checkpoint(available, settings.sd_checkpoint)
    _save(db, settings)
    log.info("auto-connected to %s at %s (checkpoint: %s)", kind, url,
             settings.sd_checkpoint or "server default")
    return settings


def _save(db: Database, settings: AppSettings) -> None:
    db.set_state("settings", settings.model_dump())


# -- generation ---------------------------------------------------------------

async def _generate_a1111(settings: AppSettings, prompt: str, out_dir: Path) -> str:
    payload = {
        "prompt": prompt, "negative_prompt": build_negative(settings),
        "seed": settings.character_seed, "width": WIDTH, "height": HEIGHT,
        "steps": 25, "sampler_name": "DPM++ 2M", "cfg_scale": 6.5,
    }
    if settings.sd_checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": settings.sd_checkpoint}
        payload["override_settings_restore_afterwards"] = False
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
        r = await client.post(settings.sd_url.rstrip("/") + "/sdapi/v1/txt2img", json=payload)
        r.raise_for_status()
        images = r.json().get("images", [])
    if not images:
        raise RuntimeError("A1111 returned no images")
    filename = f"{uuid.uuid4().hex}.png"
    (out_dir / filename).write_bytes(base64.b64decode(images[0]))
    return filename


async def _upload_reference_to_comfy(base: str, ref: Path) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{base}/upload/image",
                              files={"image": (ref.name, ref.read_bytes())},
                              data={"overwrite": "true"})
        r.raise_for_status()
        return r.json()["name"]


def _fill_workflow(template: str, settings: AppSettings, prompt: str,
                   reference_name: str | None) -> dict:
    checkpoint = settings.sd_checkpoint or "sd_xl_base_1.0.safetensors"
    filled = (template
              .replace("{{PROMPT}}", json.dumps(prompt)[1:-1])
              .replace("{{NEGATIVE}}", json.dumps(build_negative(settings))[1:-1])
              .replace("{{CHECKPOINT}}", json.dumps(checkpoint)[1:-1])
              .replace("{{SEED}}", str(settings.character_seed))
              .replace("{{WIDTH}}", str(WIDTH)).replace("{{HEIGHT}}", str(HEIGHT)))
    if reference_name is not None:
        filled = filled.replace("{{REFERENCE}}", json.dumps(reference_name)[1:-1])
    return json.loads(filled)


async def _generate_comfyui(settings: AppSettings, prompt: str, out_dir: Path,
                            photos_dir: Path) -> str:
    base = settings.sd_url.rstrip("/")
    refs = reference_images(photos_dir)
    workflow_file = WORKFLOW_DIR / ("comfy_workflow_faceid.json" if refs else "comfy_workflow.json")
    reference_name = None
    if refs:
        try:
            reference_name = await _upload_reference_to_comfy(base, refs[0])
        except Exception:
            log.info("reference upload failed, using plain workflow", exc_info=True)
            workflow_file = WORKFLOW_DIR / "comfy_workflow.json"
    workflow = _fill_workflow(workflow_file.read_text(), settings, prompt, reference_name)

    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
        r = await client.post(f"{base}/prompt", json={"prompt": workflow})
        if r.status_code >= 400 and workflow_file.name != "comfy_workflow.json":
            # FaceID nodes missing (extension not installed) -> plain workflow
            log.info("FaceID workflow rejected by ComfyUI, retrying plain: %s", r.text[:200])
            workflow = _fill_workflow((WORKFLOW_DIR / "comfy_workflow.json").read_text(),
                                      settings, prompt, None)
            r = await client.post(f"{base}/prompt", json={"prompt": workflow})
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
                          out_dir: Path, photos_dir: Path | None = None) -> str | None:
    """Returns a 'generated/<file>' path, or None on any failure."""
    if not settings.sd_enabled:
        return None
    prompt = build_prompt(settings, mood)
    try:
        if settings.sd_backend == "comfyui":
            filename = await asyncio.wait_for(
                _generate_comfyui(settings, prompt, out_dir, photos_dir or Path(".")),
                GENERATION_TIMEOUT)
        else:
            filename = await asyncio.wait_for(
                _generate_a1111(settings, prompt, out_dir), GENERATION_TIMEOUT)
    except Exception:
        log.info("SD generation failed, falling back to photo pack", exc_info=True)
        return None
    db.execute(
        "INSERT INTO photos_generated (filename, mood, prompt, backend, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (filename, mood, prompt, settings.sd_backend, now_ms()))
    return f"generated/{filename}"
