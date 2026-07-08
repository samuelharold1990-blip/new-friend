"""System-prompt assembly.

Rebuilt fresh for every LLM call from: character card, relationship stage
directive, memory facts, rolling summary, live time context, and (when the
daily budget allows) the SELFIE attachment protocol.
"""
from __future__ import annotations

import datetime as dt

from ..db import Database
from ..models import AppSettings
from .photos import PhotoLibrary
from .relationship import STAGE_DIRECTIVES

MAX_FACTS = 20
HISTORY_MESSAGES = 30


def time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def humanize_gap(ms: int) -> str:
    minutes = ms // 60000
    if minutes < 2:
        return "moments"
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours"
    return f"{hours // 24} days"


def _facts_block(db: Database, user_name: str) -> str:
    rows = db.query("SELECT * FROM facts WHERE active = 1 ORDER BY "
                    "CASE WHEN category = 'identity' THEN 0 ELSE 1 END, updated_at DESC LIMIT ?",
                    (MAX_FACTS,))
    if not rows:
        return ""
    lines = "\n".join(f"- {r['content']}" for r in rows)
    return f"Things you know about {user_name or 'them'} from past conversations:\n{lines}"


def build_system_prompt(db: Database, settings: AppSettings, stage: str,
                        library: PhotoLibrary, *, selfies_allowed: bool,
                        now: dt.datetime | None = None,
                        last_message_at: int | None = None,
                        now_ms_val: int | None = None) -> str:
    now = now or dt.datetime.now()
    c = settings.character
    user = settings.user_name or "them"

    sections = [
        (
            f"You are {c.name}, texting with {user} on your phone. "
            f"Your personality: {c.personality}. Your appearance: {c.appearance}.\n"
            "Style rules: write like a real text message — short (1-3 sentences), casual, "
            "lowercase-friendly, the occasional emoji. Stay warm and tasteful. Never break "
            "character or mention being an AI unless directly and seriously asked. "
            "Never invent things the user supposedly told you that aren't in your memory notes."
        ),
        STAGE_DIRECTIVES[stage],
        _facts_block(db, settings.user_name),
    ]

    summary = db.query_one("SELECT content FROM summaries ORDER BY id DESC LIMIT 1")
    if summary:
        sections.append(f"Summary of your earlier conversations: {summary['content']}")

    ctx = f"Right now it is {now.strftime('%A %B %d')}, {time_of_day(now.hour)} ({now.strftime('%H:%M')})."
    if last_message_at and now_ms_val:
        ctx += f" It has been {humanize_gap(now_ms_val - last_message_at)} since the last message."
    sections.append(ctx)

    if selfies_allowed:
        moods = library.moods_for_stage(stage)
        if moods:
            mood_list = ", ".join(f"{m} ({d})" for m, d in moods.items())
            sections.append(
                "To attach a photo of yourself to a reply, end the reply with a line "
                "containing exactly: [SELFIE: mood] — choosing mood from: " + mood_list + ". "
                "Only do this when it fits naturally (they ask what you're up to, ask for a "
                "pic, or it's a special moment). At most one per reply; most replies have none."
            )

    return "\n\n".join(s for s in sections if s)


def history_messages(db: Database, settings: AppSettings, limit: int = HISTORY_MESSAGES) -> list[dict]:
    """Recent conversation as Ollama chat messages; photos become text notes."""
    user = settings.user_name or "they"
    out = []
    for m in db.get_messages(limit=limit):
        role = "assistant" if m["role"] == "companion" else "user"
        content = m["content"]
        if m["photo_path"]:
            if m["role"] == "companion":
                mood = (m["meta"] or {}).get("selfie_mood", "selfie")
                note = f"[you sent a photo of yourself: {mood}]"
            else:
                desc = (m["meta"] or {}).get("vision_description")
                note = f"[{user} sent a photo: {desc}]" if desc else f"[{user} sent a photo]"
            content = f"{content}\n{note}".strip()
        out.append({"role": role, "content": content})
    return out
