"""Runtime configuration resolved from environment variables.

Everything user-tunable (Ollama URL, model, character, ...) lives in the
database instead, editable from the settings screen; this module only decides
where files live and whether we run against a mock LLM.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("COMPANION_DATA_DIR", REPO_ROOT / "data")))
    photos_dir: Path = field(default_factory=lambda: Path(os.environ.get("COMPANION_PHOTOS_DIR", REPO_ROOT / "photos")))
    static_dir: Path = REPO_ROOT / "companion" / "static"
    mock_ollama: bool = field(default_factory=lambda: os.environ.get("MOCK_OLLAMA", "") not in ("", "0", "false"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "companion.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.generated_dir):
            d.mkdir(parents=True, exist_ok=True)
