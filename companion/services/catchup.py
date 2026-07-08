"""On-open catch-up: messages she 'sent while you were away'.

No background scheduler — when the app opens after enough time away, one
JSON-mode LLM call writes 0..N short texts which are persisted with
realistically backdated timestamps inside the absence window.
"""
from __future__ import annotations

import datetime as dt
import logging
import random

from ..db import Database, now_ms
from ..models import AppSettings
from .photos import PhotoLibrary
from .prompt import build_system_prompt, time_of_day
from .relationship import CATCHUP_MIN_GAP_H, CATCHUP_N_WEIGHTS, RelationshipEngine

log = logging.getLogger(__name__)

WAKING_START, WAKING_END = 8, 23  # local hours she plausibly texts in
MAX_MESSAGES = 3
SELFIE_CHANCE = 0.20  # at close+ stages

MOOD_BY_TOD = {
    "morning": ["morning", "coffee"],
    "afternoon": ["outdoors", "coffee", "selfie_generic"],
    "evening": ["cozy", "evening"],
    "night": ["cozy", "evening"],
}


def _pick_n(stage: str, rng: random.Random) -> int:
    weights = CATCHUP_N_WEIGHTS[stage]
    choices, probs = zip(*weights.items())
    return min(rng.choices(choices, weights=probs)[0], MAX_MESSAGES)


def _sample_timestamps(n: int, start_ms: int, end_ms: int, rng: random.Random) -> list[int]:
    """n instants in (start, end), inside waking hours, >= 20 min apart."""
    def waking(ts: int) -> bool:
        return WAKING_START <= dt.datetime.fromtimestamp(ts / 1000).hour < WAKING_END

    picks: list[int] = []
    for _ in range(200):
        if len(picks) == n:
            break
        ts = rng.randint(start_ms, end_ms)
        if not waking(ts):
            continue
        if all(abs(ts - p) >= 20 * 60000 for p in picks):
            picks.append(ts)
    picks.sort()
    return picks


async def run_catchup(db: Database, settings: AppSettings, client,
                      relationship: RelationshipEngine, library: PhotoLibrary,
                      now: int | None = None, rng: random.Random | None = None) -> list[int]:
    """Returns ids of the proactive messages created (possibly empty)."""
    now = now or now_ms()
    rng = rng or random.Random()

    if not db.get_state("onboarding_complete", False):
        return []

    last_seen = db.get_state("last_seen_at")
    last_catchup = db.get_state("last_catchup_at", 0)
    state = relationship.apply_absence_decay(last_seen, now)
    stage = state["stage"]

    min_gap_h = CATCHUP_MIN_GAP_H[stage]
    if min_gap_h is None or last_seen is None:
        return []
    elapsed = now - last_seen
    if elapsed < min_gap_h * 3600 * 1000:
        return []
    if last_catchup > last_seen:  # already caught up for this absence
        return []
    if not await client.ping():
        return []

    n = _pick_n(stage, rng)
    if n == 0:
        db.set_state("last_catchup_at", now)
        return []

    window_start = last_seen + 15 * 60000
    window_end = now - 5 * 60000
    if window_end <= window_start:
        db.set_state("last_catchup_at", now)
        return []
    times = _sample_timestamps(n, window_start, window_end, rng)
    if not times:
        db.set_state("last_catchup_at", now)
        return []

    slots = ", ".join(
        f"{dt.datetime.fromtimestamp(t / 1000).strftime('%A %H:%M')} "
        f"({time_of_day(dt.datetime.fromtimestamp(t / 1000).hour)})"
        for t in times)
    user = settings.user_name or "them"
    system = build_system_prompt(db, settings, stage, library, selfies_allowed=False)
    instruction = (
        f"While {user} was away you sent {len(times)} short texts, at these times: {slots}. "
        "Write them now. Mix it up: a time-of-day-appropriate greeting, a thinking-of-you "
        "note, or a small life update of your own; reference a shared memory at most once. "
        f'Respond with ONLY JSON: {{"texts": ["...", ...]}} with exactly {len(times)} strings.'
    )

    try:
        result = await client.chat_json(
            settings.model,
            [{"role": "system", "content": system}, {"role": "user", "content": instruction}])
        texts = [str(t).strip() for t in result.get("texts", []) if str(t).strip()]
    except Exception:
        log.warning("catch-up generation failed", exc_info=True)
        return []
    if not texts:
        db.set_state("last_catchup_at", now)
        return []
    texts = texts[:len(times)]

    # maybe attach one pack photo (never SD — app open must stay fast)
    photo_idx, photo_path, photo_mood = -1, None, None
    if stage in ("close", "romantic") and relationship.selfies_remaining_today(now) > 0 \
            and rng.random() < SELFIE_CHANCE:
        photo_idx = rng.randrange(len(texts))
        tod = time_of_day(dt.datetime.fromtimestamp(times[photo_idx] / 1000).hour)
        for mood in MOOD_BY_TOD[tod]:
            photo_path = library.pick(mood, stage)
            if photo_path:
                photo_mood = mood
                break

    ids = []
    for i, (text, ts) in enumerate(zip(texts, times)):
        has_photo = i == photo_idx and photo_path
        ids.append(db.add_message(
            "companion", text,
            photo_path=photo_path if has_photo else None,
            photo_kind="pack" if has_photo else None,
            is_proactive=True, created_at=ts,
            meta={"selfie_mood": photo_mood} if has_photo else None))
        if has_photo:
            relationship.record_selfie(now)

    db.set_state("last_catchup_at", now)
    return ids
