"""Her own daily life: a small per-day plan that keeps her world coherent.

One LLM call per day invents what she's up to (morning/afternoon/evening),
cached in app_state. The plan feeds the system prompt, so "what are you up
to?" gets the same answer at 2pm and 4pm, catch-up texts reference real
'events' from her day, and her selfie moods match what she said she was
doing. A deterministic fallback keeps it working when the LLM is down.
"""
from __future__ import annotations

import datetime as dt
import logging
import random

from ..db import Database
from ..models import AppSettings
from .prompt import time_of_day

log = logging.getLogger(__name__)

PLAN_SLOTS = ("morning", "afternoon", "evening")

PLAN_INSTRUCTION = (
    "Invent your own small, ordinary day for {date} ({weekday}), consistent with your "
    "personality. Respond with ONLY JSON: "
    '{{"morning": "...", "afternoon": "...", "evening": "..."}} — one short phrase each '
    "(e.g. \"went for a run by the river\", \"working from the cafe on Fifth\", "
    "\"movie night with popcorn\"). Keep it everyday and specific; no grand adventures."
)

# fallback pools, rotated deterministically by date so the day stays stable
FALLBACK = {
    "morning": ["slow morning with coffee and a playlist", "went for an early walk",
                "did a little yoga and made pancakes", "tidied the apartment with music on"],
    "afternoon": ["errands and a bit of window shopping", "reading in the sun",
                  "editing photos from the weekend", "catching up with a friend over lunch"],
    "evening": ["cooking something new for dinner", "curled up with a show",
                "sorting my camera roll and journaling", "long bath and an early night"],
}

MOOD_HINTS = {
    "run": "gym", "gym": "gym", "workout": "gym", "yoga": "gym",
    "coffee": "coffee", "cafe": "coffee", "brunch": "coffee",
    "walk": "outdoors", "park": "outdoors", "errands": "outdoors", "shopping": "outdoors",
    "dinner": "evening", "movie": "cozy", "show": "cozy", "reading": "cozy",
    "bath": "cozy", "journal": "cozy", "night": "evening",
}


def _fallback_plan(date_str: str) -> dict:
    rng = random.Random(date_str)
    return {slot: rng.choice(pool) for slot, pool in FALLBACK.items()}


async def get_today_plan(db: Database, settings: AppSettings, client,
                         now: dt.datetime | None = None) -> dict:
    """Returns {'morning': ..., 'afternoon': ..., 'evening': ...} for today."""
    now = now or dt.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    cached = db.get_state("life_plan")
    if cached and cached.get("date") == date_str:
        return cached["plan"]

    plan = None
    try:
        c = settings.character
        system = (f"You are {c.name}. Personality: {c.personality}. "
                  "You live a normal, pleasant everyday life.")
        result = await client.chat_json(settings.model, [
            {"role": "system", "content": system},
            {"role": "user", "content": PLAN_INSTRUCTION.format(
                date=now.strftime("%B %d"), weekday=now.strftime("%A"))},
        ])
        if all(isinstance(result.get(s), str) and result[s].strip() for s in PLAN_SLOTS):
            plan = {s: result[s].strip() for s in PLAN_SLOTS}
    except Exception:
        log.info("life plan generation failed, using fallback", exc_info=True)
    if plan is None:
        plan = _fallback_plan(date_str)

    db.set_state("life_plan", {"date": date_str, "plan": plan})
    return plan


def life_block(plan: dict, now: dt.datetime | None = None) -> str:
    """Prompt section describing her day, marking where she is in it."""
    now = now or dt.datetime.now()
    tod = time_of_day(now.hour)
    current = "evening" if tod == "night" else tod
    lines = []
    for slot in PLAN_SLOTS:
        marker = "  <- this is what you're doing now" if slot == current else ""
        lines.append(f"- {slot}: {plan[slot]}{marker}")
    return ("Your own day today (be consistent about this if asked what you're up to):\n"
            + "\n".join(lines))


def suggest_mood(plan: dict, now: dt.datetime | None = None) -> str | None:
    """A selfie mood matching what she's doing right now, if any keyword hits."""
    now = now or dt.datetime.now()
    tod = time_of_day(now.hour)
    current = plan.get("evening" if tod == "night" else tod, "")
    for keyword, mood in MOOD_HINTS.items():
        if keyword in current.lower():
            return mood
    return None
