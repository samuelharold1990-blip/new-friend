"""Relationship progression: score + minimum-tenure gated stages.

Scoring: +1 per user message (cap +15/day), +3 per distinct day with any
conversation, +2 per newly learned fact (cap +6/day). Absence beyond 3 days
decays 2 points per extra day, floored at the current stage's threshold so
she cools off but never demotes. Advancing needs BOTH the score and a minimum
number of days since the first chat — no maxing her out in one marathon night.
"""
from __future__ import annotations

import datetime as dt

from ..db import Database, now_ms

DAY_MS = 24 * 3600 * 1000

# name, score threshold, min days since first chat
STAGES = [
    ("new", 0, 0),
    ("friendly", 30, 2),
    ("close", 100, 7),
    ("romantic", 250, 21),
]
STAGE_NAMES = [s[0] for s in STAGES]

STAGE_DIRECTIVES = {
    "new": (
        "You two only recently started talking. Be friendly, upbeat and curious — "
        "you're getting to know each other. Ask questions about their life. "
        "No pet names yet, and don't be overly familiar."
    ),
    "friendly": (
        "You're good friends now. Be warm and playful, tease lightly, and show that "
        "you remember the details they've shared. You enjoy talking to them and it shows."
    ),
    "close": (
        "You're very close. Be openly affectionate, say you missed them when they've been "
        "away, use an occasional pet name, and often reference your shared history and "
        "inside references from past conversations."
    ),
    "romantic": (
        "You're each other's favorite person. Be openly loving and comfortable — "
        "'thinking of you' energy, in-jokes, easy affection. You know their life well "
        "and weave it naturally into what you say."
    ),
}

# per-stage behavior knobs
SELFIES_PER_DAY = {"new": 0, "friendly": 1, "close": 2, "romantic": 3}
CATCHUP_MIN_GAP_H = {"new": None, "friendly": 12, "close": 4, "romantic": 2}
CATCHUP_N_WEIGHTS = {
    "new": {0: 1.0},
    "friendly": {0: 0.5, 1: 0.5},
    "close": {0: 0.2, 1: 0.5, 2: 0.3},
    "romantic": {1: 0.4, 2: 0.4, 3: 0.2},
}

MSG_PTS_DAILY_CAP = 15
FACT_PTS_DAILY_CAP = 6


def _date_str(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


def _default_state(now: int) -> dict:
    return {
        "stage": "new", "score": 0,
        "first_chat_at": now, "stage_entered_at": now,
        "last_decay_at": now,
        "day": _date_str(now), "day_msg_pts": 0, "day_fact_pts": 0, "day_counted": False,
    }


class RelationshipEngine:
    def __init__(self, db: Database):
        self.db = db

    def get(self, now: int | None = None) -> dict:
        now = now or now_ms()
        state = self.db.get_state("relationship")
        if state is None:
            state = _default_state(now)
            self.db.set_state("relationship", state)
        return state

    def _save(self, state: dict) -> None:
        self.db.set_state("relationship", state)

    def _roll_day(self, state: dict, now: int) -> None:
        today = _date_str(now)
        if state["day"] != today:
            state["day"] = today
            state["day_msg_pts"] = 0
            state["day_fact_pts"] = 0
            state["day_counted"] = False

    def _check_advance(self, state: dict, now: int) -> None:
        days_since_start = (now - state["first_chat_at"]) / DAY_MS
        idx = STAGE_NAMES.index(state["stage"])
        while idx + 1 < len(STAGES):
            _, threshold, min_days = STAGES[idx + 1]
            if state["score"] >= threshold and days_since_start >= min_days:
                idx += 1
                state["stage"] = STAGES[idx][0]
                state["stage_entered_at"] = now
            else:
                break

    def add_user_message_points(self, now: int | None = None) -> dict:
        now = now or now_ms()
        state = self.get(now)
        self._roll_day(state, now)
        if state["day_msg_pts"] < MSG_PTS_DAILY_CAP:
            state["day_msg_pts"] += 1
            state["score"] += 1
        if not state["day_counted"]:
            state["day_counted"] = True
            state["score"] += 3
        self._check_advance(state, now)
        self._save(state)
        return state

    def add_fact_points(self, n_facts: int, now: int | None = None) -> dict:
        now = now or now_ms()
        state = self.get(now)
        self._roll_day(state, now)
        budget = FACT_PTS_DAILY_CAP - state["day_fact_pts"]
        pts = min(n_facts * 2, max(0, budget))
        state["day_fact_pts"] += pts
        state["score"] += pts
        self._check_advance(state, now)
        self._save(state)
        return state

    def apply_absence_decay(self, last_seen_at: int | None, now: int | None = None) -> dict:
        """-2 per full day of absence beyond 3, floored at the stage threshold."""
        now = now or now_ms()
        state = self.get(now)
        if last_seen_at:
            absent_days = (now - last_seen_at) / DAY_MS
            decayable = int(absent_days) - 3
            if decayable > 0 and state["last_decay_at"] < last_seen_at + 3 * DAY_MS:
                floor = next(t for n, t, _ in STAGES if n == state["stage"])
                state["score"] = max(floor, state["score"] - 2 * decayable)
                state["last_decay_at"] = now
                self._save(state)
        return state

    # -- selfie daily budget -------------------------------------------------

    def selfies_remaining_today(self, now: int | None = None) -> int:
        now = now or now_ms()
        state = self.get(now)
        counts = self.db.get_state("selfie_counts", {})
        today = _date_str(now)
        used = counts.get(today, 0)
        return max(0, SELFIES_PER_DAY[state["stage"]] - used)

    def record_selfie(self, now: int | None = None) -> None:
        now = now or now_ms()
        today = _date_str(now)
        counts = {today: self.db.get_state("selfie_counts", {}).get(today, 0) + 1}
        self.db.set_state("selfie_counts", counts)
