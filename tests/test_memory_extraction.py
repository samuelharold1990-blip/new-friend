"""Fact merge/dedupe logic."""
from companion.db import Database
from companion.services.memory import merge_extraction


def make_db(tmp_path):
    return Database(tmp_path / "t.db")


def test_new_facts_and_summary_inserted(tmp_path):
    db = make_db(tmp_path)
    n = merge_extraction(db, {
        "new_facts": [
            {"category": "identity", "content": "User's name is Sam"},
            {"category": "people", "content": "User's sister Emma lives in Denver"},
        ],
        "updated_facts": [],
        "summary": "Getting to know each other.",
    }, up_to_message_id=10)
    assert n == 2
    facts = db.query("SELECT * FROM facts WHERE active = 1")
    assert len(facts) == 2
    assert db.query_one("SELECT content FROM summaries")["content"] == "Getting to know each other."


def test_near_duplicates_deduped(tmp_path):
    db = make_db(tmp_path)
    merge_extraction(db, {"new_facts": [{"category": "hobbies", "content": "User loves rock climbing"}],
                          "summary": ""}, up_to_message_id=1)
    n = merge_extraction(db, {"new_facts": [{"category": "hobbies", "content": "The user loves rock climbing"}],
                              "summary": ""}, up_to_message_id=2)
    assert n == 0
    assert len(db.query("SELECT * FROM facts WHERE active = 1")) == 1


def test_updated_facts_applied_by_id(tmp_path):
    db = make_db(tmp_path)
    merge_extraction(db, {"new_facts": [{"category": "work", "content": "User works at Acme"}],
                          "summary": ""}, up_to_message_id=1)
    fid = db.query_one("SELECT id FROM facts")["id"]
    merge_extraction(db, {"new_facts": [],
                          "updated_facts": [{"id": fid, "content": "User is a senior engineer at Acme"}],
                          "summary": ""}, up_to_message_id=2)
    assert db.query_one("SELECT content FROM facts WHERE id = ?", (fid,))["content"] == \
        "User is a senior engineer at Acme"


def test_bad_categories_and_blanks_handled(tmp_path):
    db = make_db(tmp_path)
    n = merge_extraction(db, {
        "new_facts": [
            {"category": "nonsense", "content": "User likes tea"},
            {"category": "hobbies", "content": "   "},
        ],
        "summary": "",
    }, up_to_message_id=1)
    assert n == 1
    fact = db.query_one("SELECT * FROM facts WHERE active = 1")
    assert fact["category"] == "other"
