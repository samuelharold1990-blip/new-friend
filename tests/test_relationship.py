"""Relationship engine: scoring caps, stage gates, decay — with a frozen clock."""
from companion.db import Database
from companion.services.relationship import DAY_MS, RelationshipEngine

T0 = 1_750_000_000_000  # an arbitrary fixed epoch-ms anchor


def make_engine(tmp_path):
    db = Database(tmp_path / "t.db")
    return RelationshipEngine(db), db


def test_daily_message_cap(tmp_path):
    eng, _ = make_engine(tmp_path)
    for _ in range(50):
        eng.add_user_message_points(now=T0)
    state = eng.get(T0)
    # 15 capped message points + 3 for the first chat day
    assert state["score"] == 18


def test_day_bonus_once_per_day(tmp_path):
    eng, _ = make_engine(tmp_path)
    eng.add_user_message_points(now=T0)
    eng.add_user_message_points(now=T0)
    assert eng.get(T0)["score"] == 2 + 3
    eng.add_user_message_points(now=T0 + DAY_MS)
    assert eng.get(T0)["score"] == 3 + 3 + 3


def test_fact_points_capped(tmp_path):
    eng, _ = make_engine(tmp_path)
    eng.add_fact_points(10, now=T0)  # 20 pts requested, cap 6/day
    assert eng.get(T0)["score"] == 6


def test_stage_needs_both_score_and_tenure(tmp_path):
    eng, _ = make_engine(tmp_path)
    # grind hard on day one: score passes 30 but tenure (2 days) doesn't
    for day in range(3):
        for _ in range(20):
            eng.add_user_message_points(now=T0 + day * DAY_MS)
    state = eng.get()
    assert state["score"] >= 30
    assert state["stage"] == "friendly"  # reached only once 2 days passed
    # a single marathon day can never leave 'new'
    eng2, _ = make_engine(tmp_path / "sub" if (tmp_path / "sub").mkdir() is None else tmp_path)
    for _ in range(100):
        eng2.add_user_message_points(now=T0)
    assert eng2.get(T0)["stage"] == "new"


def test_absence_decay_floors_at_stage_threshold(tmp_path):
    eng, db = make_engine(tmp_path)
    state = eng.get(T0)
    state.update(stage="friendly", score=40)
    db.set_state("relationship", state)
    # gone 10 days -> 7 decayable days -> -14, floor 30
    out = eng.apply_absence_decay(last_seen_at=T0, now=T0 + 10 * DAY_MS)
    assert out["score"] == 30
    # short absences don't decay
    eng2, db2 = make_engine(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    s2 = eng2.get(T0)
    s2.update(score=10)
    db2.set_state("relationship", s2)
    assert eng2.apply_absence_decay(T0, now=T0 + 2 * DAY_MS)["score"] == 10


def test_selfie_budget(tmp_path):
    eng, db = make_engine(tmp_path)
    assert eng.selfies_remaining_today(T0) == 0  # 'new' stage: no selfies
    state = eng.get(T0)
    state["stage"] = "close"
    db.set_state("relationship", state)
    assert eng.selfies_remaining_today(T0) == 2
    eng.record_selfie(T0)
    assert eng.selfies_remaining_today(T0) == 1
