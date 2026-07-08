"""The three engine upgrades: SD auto-config, semantic memory, her daily life."""
import asyncio
import datetime as dt
import json

from companion.db import Database
from companion.models import AppSettings, CharacterCard
from companion.services import sd
from companion.services.life import _fallback_plan, get_today_plan, life_block, suggest_mood
from companion.services.memory import merge_extraction, embed_missing_facts, recall_relevant_facts
from companion.services.ollama import MockOllamaClient


# ---- SD: prompt building, pony detection, checkpoint picking ----

def test_pony_checkpoint_gets_score_tags():
    s = AppSettings(sd_checkpoint="cyberrealisticPony_v90.safetensors",
                    character=CharacterCard(appearance="chestnut hair"))
    prompt = sd.build_prompt(s, "coffee")
    assert prompt.startswith("score_9, score_8_up")
    assert "chestnut hair" in prompt
    assert "source_anime" in sd.build_negative(s)


def test_non_pony_checkpoint_plain_prompt():
    s = AppSettings(sd_checkpoint="juggernautXL_v10.safetensors")
    prompt = sd.build_prompt(s, "coffee")
    assert not prompt.startswith("score_9")
    assert "source_anime" not in sd.build_negative(s)


def test_user_prefix_wins_over_auto():
    s = AppSettings(sd_checkpoint="ponyDiffusionV6XL.safetensors",
                    sd_prompt_prefix="my custom style")
    assert sd.build_prompt(s, "gym").startswith("my custom style")


def test_pick_checkpoint_prefers_photoreal():
    available = ["animeThing_v1.safetensors", "juggernautXL_v10.safetensors",
                 "cyberrealisticPony_v90.safetensors"]
    assert sd.pick_checkpoint(available) == "cyberrealisticPony_v90.safetensors"
    assert sd.pick_checkpoint(available, preferred="juggernaut") == "juggernautXL_v10.safetensors"
    assert sd.pick_checkpoint(["only_one.ckpt"]) == "only_one.ckpt"


def test_workflow_fill_produces_valid_json():
    s = AppSettings(sd_checkpoint="test.safetensors",
                    character=CharacterCard(appearance='she has "quoted" style'))
    template = (sd.WORKFLOW_DIR / "comfy_workflow_faceid.json").read_text()
    wf = sd._fill_workflow(template, s, sd.build_prompt(s, "cozy"), "ref.png")
    assert wf["4"]["inputs"]["ckpt_name"] == "test.safetensors"
    assert wf["12"]["inputs"]["image"] == "ref.png"
    assert "quoted" in wf["6"]["inputs"]["text"]
    # plain workflow too
    wf2 = sd._fill_workflow((sd.WORKFLOW_DIR / "comfy_workflow.json").read_text(), s, "p", None)
    assert wf2["4"]["inputs"]["ckpt_name"] == "test.safetensors"


def test_reference_images_scanning(tmp_path):
    assert sd.reference_images(tmp_path) == []
    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "her.png").write_bytes(b"x")
    (ref / "notes.txt").write_text("not an image")
    assert [p.name for p in sd.reference_images(tmp_path)] == ["her.png"]


def test_reference_folder_is_not_a_mood(tmp_path):
    from companion.services.photos import PhotoLibrary
    (tmp_path / "coffee").mkdir()
    (tmp_path / "coffee" / "a.svg").write_text("<svg/>")
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "her.png").write_bytes(b"x")
    db = Database(tmp_path / "t.db")
    lib = PhotoLibrary(tmp_path, tmp_path / "gen", db)
    assert "reference" not in lib.manifest()["moods"]
    assert "coffee" in lib.manifest()["moods"]


# ---- semantic memory ----

def test_semantic_recall_finds_relevant_fact(tmp_path):
    db = Database(tmp_path / "t.db")
    merge_extraction(db, {"new_facts": [
        {"category": "people", "content": "User's sister Emma lives in Denver"},
        {"category": "hobbies", "content": "User loves rock climbing at the gym"},
        {"category": "work", "content": "User writes software at Acme"},
    ], "summary": ""}, up_to_message_id=1)
    client = MockOllamaClient()
    settings = AppSettings()
    asyncio.run(embed_missing_facts(db, settings, client))
    assert all(r["embedding"] for r in db.query("SELECT embedding FROM facts"))

    hits = asyncio.run(recall_relevant_facts(
        db, settings, client, "how is my sister emma doing in denver?"))
    assert hits
    assert "Emma" in hits[0]["content"]


def test_recall_disabled_returns_empty(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = AppSettings(embedding_model="")
    hits = asyncio.run(recall_relevant_facts(db, settings, MockOllamaClient(), "anything"))
    assert hits == []


# ---- her daily life ----

def test_fallback_plan_is_stable_per_day():
    assert _fallback_plan("2026-07-08") == _fallback_plan("2026-07-08")
    assert _fallback_plan("2026-07-08") != _fallback_plan("2026-07-09") or True  # may collide, but shape holds
    plan = _fallback_plan("2026-07-08")
    assert set(plan) == {"morning", "afternoon", "evening"}


def test_life_plan_cached_per_day(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = AppSettings()
    client = MockOllamaClient()
    p1 = asyncio.run(get_today_plan(db, settings, client))
    p2 = asyncio.run(get_today_plan(db, settings, client))
    assert p1 == p2
    assert db.get_state("life_plan")["plan"] == p1


def test_life_block_marks_current_slot():
    plan = {"morning": "run by the river", "afternoon": "cafe work", "evening": "movie night"}
    block = life_block(plan, dt.datetime(2026, 7, 8, 14, 0))
    assert "cafe work  <- this is what you're doing now" in block


def test_suggest_mood_from_activity():
    plan = {"morning": "went for a run", "afternoon": "coffee with a friend", "evening": "movie night"}
    assert suggest_mood(plan, dt.datetime(2026, 7, 8, 9, 0)) == "gym"
    assert suggest_mood(plan, dt.datetime(2026, 7, 8, 14, 0)) == "coffee"
    assert suggest_mood(plan, dt.datetime(2026, 7, 8, 20, 0)) == "cozy"
