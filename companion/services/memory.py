"""Memory: LLM-driven fact extraction and a rolling conversation summary.

Runs as a fire-and-forget task after replies — never blocks chat, and any
failure is silently skipped (extraction is best-effort by design).
"""
from __future__ import annotations

import difflib
import json
import logging

from ..db import Database, now_ms
from ..models import AppSettings
from .relationship import RelationshipEngine

log = logging.getLogger(__name__)

CATEGORIES = {"identity", "work", "hobbies", "people", "events", "preferences", "other"}
MIN_NEW_USER_MESSAGES = 8
STALE_HOURS = 24
STALE_MIN_MESSAGES = 3
DEDUPE_RATIO = 0.85

EXTRACTION_INSTRUCTIONS = """\
You maintain memory notes about a person based on their chat messages.
Given the conversation excerpt, the existing notes and the current summary,
respond with ONLY a JSON object of this exact shape:
{"new_facts": [{"category": "identity|work|hobbies|people|events|preferences|other",
                "content": "one short sentence about the user"}],
 "updated_facts": [{"id": 123, "content": "corrected sentence"}],
 "summary": "a 150-200 word rolling summary of the whole relationship so far"}
Only record durable facts about the USER (their name, job, people in their life,
hobbies, upcoming events, likes/dislikes). Do not record small talk. If there is
nothing new, use empty lists but still return an updated summary."""


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def should_extract(db: Database, now: int | None = None) -> bool:
    now = now or now_ms()
    last_id = db.get_state("last_extraction_message_id", 0)
    rows = db.query("SELECT COUNT(*) AS n FROM messages WHERE role = 'user' AND id > ?", (last_id,))
    new_user_msgs = rows[0]["n"]
    if new_user_msgs >= MIN_NEW_USER_MESSAGES:
        return True
    last_at = db.get_state("last_extraction_at", 0)
    return new_user_msgs >= STALE_MIN_MESSAGES and (now - last_at) > STALE_HOURS * 3600 * 1000


async def run_extraction(db: Database, settings: AppSettings, client,
                         relationship: RelationshipEngine) -> None:
    try:
        last_id = db.get_state("last_extraction_message_id", 0)
        messages = db.query(
            "SELECT id, role, content FROM messages WHERE id > ? ORDER BY id LIMIT 60", (last_id,))
        if not messages:
            return
        transcript = "\n".join(
            f"{'user' if m['role'] == 'user' else 'companion'}: {m['content']}" for m in messages)
        existing = db.query("SELECT id, content FROM facts WHERE active = 1")
        existing_block = "\n".join(f"[{f['id']}] {f['content']}" for f in existing) or "(none yet)"
        summary_row = db.query_one("SELECT content FROM summaries ORDER BY id DESC LIMIT 1")

        payload = (
            f"{EXTRACTION_INSTRUCTIONS}\n\nExisting notes:\n{existing_block}\n\n"
            f"Current summary: {summary_row['content'] if summary_row else '(none yet)'}\n\n"
            f"Conversation excerpt:\n{transcript}"
        )
        try:
            result = await client.chat_json(settings.model, [{"role": "user", "content": payload}])
        except Exception:
            result = await client.chat_json(settings.model, [{"role": "user", "content": payload}])

        merge_extraction(db, result, up_to_message_id=messages[-1]["id"],
                         relationship=relationship)
        db.set_state("last_extraction_message_id", messages[-1]["id"])
        db.set_state("last_extraction_at", now_ms())
    except Exception:
        log.warning("memory extraction skipped", exc_info=True)


def merge_extraction(db: Database, result: dict, *, up_to_message_id: int,
                     relationship: RelationshipEngine | None = None) -> int:
    """Apply an extraction result; returns how many genuinely new facts landed."""
    now = now_ms()
    existing = db.query("SELECT id, content FROM facts WHERE active = 1")
    new_count = 0

    for fact in result.get("new_facts", []) or []:
        content = (fact.get("content") or "").strip()
        if not content:
            continue
        category = fact.get("category", "other")
        if category not in CATEGORIES:
            category = "other"
        dup = next((e for e in existing
                    if difflib.SequenceMatcher(None, _normalize(e["content"]),
                                               _normalize(content)).ratio() > DEDUPE_RATIO), None)
        if dup:
            db.execute("UPDATE facts SET updated_at = ? WHERE id = ?", (now, dup["id"]))
        else:
            db.execute(
                "INSERT INTO facts (category, content, source_message_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)", (category, content, up_to_message_id, now, now))
            existing.append({"id": -1, "content": content})
            new_count += 1

    for fact in result.get("updated_facts", []) or []:
        fid, content = fact.get("id"), (fact.get("content") or "").strip()
        if isinstance(fid, int) and content:
            db.execute("UPDATE facts SET content = ?, updated_at = ? WHERE id = ? AND active = 1",
                       (content, now, fid))

    summary = (result.get("summary") or "").strip()
    if summary:
        db.execute("INSERT INTO summaries (up_to_message_id, content, created_at) VALUES (?, ?, ?)",
                   (up_to_message_id, summary, now))

    if new_count and relationship:
        relationship.add_fact_points(new_count)
    return new_count
