"""End-to-end API tests against the mock LLM."""
import json


def parse_sse(body: str):
    events = []
    for frame in body.split("\n\n"):
        event, data = None, ""
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data += line[6:]
        if event:
            events.append((event, json.loads(data)))
    return events


def test_health_reports_mock(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["mock_mode"] is True
    assert body["ollama"]["reachable"] is True


def test_onboarding_seeds_greeting(client, onboarded):
    msgs = client.get("/api/messages").json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "companion"
    assert msgs[0]["content"]


def test_chat_streams_and_persists(client, onboarded):
    r = client.post("/api/chat", json={"text": "hey, how are you?"})
    assert r.status_code == 200
    events = parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert "token" in kinds
    assert kinds[-1] == "done"
    done = events[-1][1]
    assert done["user_message"]["content"] == "hey, how are you?"
    assert done["reply"]["content"]
    assert "[SELFIE" not in done["reply"]["content"]
    msgs = client.get("/api/messages").json()["messages"]
    assert len(msgs) == 3  # greeting + user + reply


def test_selfie_flow_attaches_photo(client, onboarded, app):
    # 'new' stage has no selfie budget — bump to friendly for the test
    db = app.state.db
    state = app.state.relationship.get()
    state["stage"] = "friendly"
    db.set_state("relationship", state)

    r = client.post("/api/chat", json={"text": "can you send me a selfie?"})
    events = parse_sse(r.text)
    photo_events = [d for e, d in events if e == "photo"]
    assert photo_events, f"no photo event in {[e for e, _ in events]}"
    assert photo_events[0]["mood"] == "coffee"
    done = [d for e, d in events if e == "done"][0]
    assert done["reply"]["photo_path"]
    assert "SELFIE" not in done["reply"]["content"]
    # the tag never leaked into the streamed tokens either
    streamed = "".join(d["text"] for e, d in events if e == "token")
    assert "SELFIE" not in streamed


def test_selfie_budget_respected(client, onboarded, app):
    db = app.state.db
    state = app.state.relationship.get()
    state["stage"] = "friendly"  # 1 selfie/day
    db.set_state("relationship", state)

    r1 = client.post("/api/chat", json={"text": "send me a selfie please"})
    assert any(e == "photo" for e, _ in parse_sse(r1.text))
    r2 = client.post("/api/chat", json={"text": "one more selfie please"})
    assert not any(e == "photo" for e, _ in parse_sse(r2.text))


def test_settings_round_trip(client):
    s = client.get("/api/settings").json()
    s["character"]["name"] = "Nova"
    s["user_name"] = "Alex"
    r = client.put("/api/settings", json=s)
    assert r.status_code == 200
    again = client.get("/api/settings").json()
    assert again["character"]["name"] == "Nova"
    assert again["user_name"] == "Alex"


def test_memory_endpoints(client, onboarded, app):
    from companion.services.memory import merge_extraction
    merge_extraction(app.state.db, {
        "new_facts": [{"category": "identity", "content": "User's name is Sam"}],
        "summary": "s",
    }, up_to_message_id=1)
    body = client.get("/api/memory/facts").json()
    assert body["relationship"]["stage"] == "new"
    assert len(body["facts"]) == 1
    fid = body["facts"][0]["id"]
    assert client.delete(f"/api/memory/facts/{fid}").status_code == 200
    assert client.get("/api/memory/facts").json()["facts"] == []


def test_manifest_lists_shipped_moods(client):
    moods = client.get("/api/photos/manifest").json()["moods"]
    for expected in ("morning", "coffee", "cozy", "dressed_up", "selfie_generic"):
        assert expected in moods
        assert moods[expected]["files"]


def test_export_and_wipe(client, onboarded):
    export = client.get("/api/data/export")
    assert export.status_code == 200
    assert export.json()["messages"]
    r = client.post("/api/data/wipe", json={"confirm": "DELETE"})
    assert r.status_code == 200
    assert client.get("/api/messages").json()["messages"] == []
    assert client.get("/api/health").json()["onboarding_complete"] is False


def test_wipe_requires_confirmation(client):
    assert client.post("/api/data/wipe", json={"confirm": "nope"}).status_code == 400
