import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companion.config import Config, REPO_ROOT  # noqa: E402
from companion.main import create_app  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    config = Config(
        data_dir=tmp_path / "data",
        photos_dir=REPO_ROOT / "photos",
        mock_ollama=True,
    )
    return create_app(config)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(app):
    return app.state.db


@pytest.fixture()
def onboarded(client):
    r = client.post("/api/onboarding/complete", json={
        "model": "mock-chat:latest",
        "user_name": "Sam",
        "character": {"name": "Mira", "personality": "warm", "appearance": "chestnut hair"},
    })
    assert r.status_code == 200
    return r.json()
