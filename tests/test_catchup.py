"""On-open catch-up: guards, backdating bounds, idempotency — frozen time."""
import asyncio
import random

from companion.config import Config, REPO_ROOT
from companion.db import Database
from companion.models import AppSettings
from companion.services.catchup import run_catchup
from companion.services.ollama import MockOllamaClient
from companion.services.photos import PhotoLibrary
from companion.services.relationship import DAY_MS, RelationshipEngine

T0 = 1_750_000_000_000


def setup(tmp_path, stage="close"):
    db = Database(tmp_path / "t.db")
    db.set_state("onboarding_complete", True)
    eng = RelationshipEngine(db)
    state = eng.get(T0)
    state["stage"] = stage
    db.set_state("relationship", state)
    config = Config(data_dir=tmp_path / "data", photos_dir=REPO_ROOT / "photos", mock_ollama=True)
    config.ensure_dirs()
    library = PhotoLibrary(config.photos_dir, config.generated_dir, db)
    return db, eng, library


def run(db, eng, library, now, seed=7):
    return asyncio.run(run_catchup(
        db, AppSettings(), MockOllamaClient(), eng, library,
        now=now, rng=random.Random(seed)))


def test_no_catchup_below_threshold(tmp_path):
    db, eng, library = setup(tmp_path)  # close: 4h threshold
    db.set_state("last_seen_at", T0)
    assert run(db, eng, library, now=T0 + 3600 * 1000) == []


def test_catchup_creates_backdated_messages(tmp_path):
    db, eng, library = setup(tmp_path)
    last_seen = T0
    now = T0 + DAY_MS  # away a full day
    db.set_state("last_seen_at", last_seen)
    ids = run(db, eng, library, now=now)
    assert ids  # close stage after 24h should usually produce messages with this seed
    for row in db.query("SELECT * FROM messages"):
        assert row["is_proactive"] == 1
        assert last_seen < row["created_at"] < now
    # ascending timestamps
    times = [r["created_at"] for r in db.query("SELECT created_at FROM messages ORDER BY id")]
    assert times == sorted(times)


def test_idempotent_per_absence(tmp_path):
    db, eng, library = setup(tmp_path)
    db.set_state("last_seen_at", T0)
    first = run(db, eng, library, now=T0 + DAY_MS)
    again = run(db, eng, library, now=T0 + DAY_MS + 60000)
    assert first
    assert again == []  # already caught up for this absence


def test_new_stage_never_catches_up(tmp_path):
    db, eng, library = setup(tmp_path, stage="new")
    db.set_state("last_seen_at", T0)
    assert run(db, eng, library, now=T0 + 7 * DAY_MS) == []
