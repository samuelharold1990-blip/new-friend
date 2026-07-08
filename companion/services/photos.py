"""Photo pack: mood manifest, selection, and the [SELFIE: mood] tag protocol.

She attaches photos by ending a reply with a line like `[SELFIE: coffee]`.
SelfieTagFilter sits between the Ollama token stream and the SSE output so
the tag never flickers into the UI; a regex safety net on the final text
catches malformed variants.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from ..db import Database
from .relationship import STAGE_NAMES

IMAGE_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}

# mood -> (description used in prompts, minimum stage that unlocks it)
DEFAULT_MOOD_META = {
    "morning": ("just woke up, cozy morning light", "friendly"),
    "coffee": ("out at a cafe or holding a fresh coffee", "friendly"),
    "gym": ("just finished a workout, sporty", "friendly"),
    "outdoors": ("out on a walk, park or city streets", "friendly"),
    "selfie_generic": ("a casual everyday selfie", "friendly"),
    "evening": ("evening, warm indoor lighting", "close"),
    "cozy": ("curled up at home, blanket and comfy clothes", "close"),
    "dressed_up": ("dressed up nicely for an evening out", "romantic"),
}

COMPLETE_TAG = re.compile(r"\[\s*SELFIE\s*:?\s*([A-Za-z_ \-]+?)\s*\]", re.I)
TRAILING_TAG = re.compile(r"\[\s*SELFIE\s*:?\s*([A-Za-z_ \-]+?)\s*\]?\s*$", re.I)

_MAX_WITHHELD = 64


def _viable_tag_prefix(s: str) -> bool:
    """True if s (which starts with '[') could still grow into a SELFIE tag."""
    i, n = 1, len(s)
    while i < n and s[i] in " \t":
        i += 1
    word = "selfie"
    j = 0
    while i < n and j < len(word) and s[i].lower() == word[j]:
        i += 1
        j += 1
    if i == n:
        return True  # still growing through (or before) the keyword
    if j < len(word):
        return False  # diverged from 'selfie'
    while i < n and s[i] in " :\t":
        i += 1
    while i < n and (s[i].isalnum() or s[i] in "_ -"):
        i += 1
    if i == n:
        return True  # mood still growing
    return s[i] == "]"


class SelfieTagFilter:
    """Feed streamed chunks in, get user-safe text out; captures the mood."""

    def __init__(self):
        self.buf = ""
        self.mood: str | None = None

    def _scan(self, at_end: bool) -> str:
        out: list[str] = []
        while True:
            idx = self.buf.find("[")
            if idx == -1:
                out.append(self.buf)
                self.buf = ""
                break
            out.append(self.buf[:idx])
            self.buf = self.buf[idx:]
            m = COMPLETE_TAG.match(self.buf)
            if m:
                self.mood = m.group(1).strip().lower().replace(" ", "_")
                self.buf = self.buf[m.end():]
                continue
            if not at_end and _viable_tag_prefix(self.buf) and len(self.buf) < _MAX_WITHHELD:
                break  # withhold; might complete in a later chunk
            if at_end:
                m = TRAILING_TAG.match(self.buf)
                if m:  # tag truncated at end of stream (e.g. missing ']')
                    self.mood = m.group(1).strip().lower().replace(" ", "_")
                    self.buf = ""
                    break
            out.append("[")
            self.buf = self.buf[1:]
        return "".join(out)

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        return self._scan(at_end=False)

    def flush(self) -> str:
        return self._scan(at_end=True)


def strip_selfie_tags(text: str) -> tuple[str, str | None]:
    """Safety net: remove any tag from final text, return (clean, mood)."""
    mood = None
    m = COMPLETE_TAG.search(text)
    if m:
        mood = m.group(1).strip().lower().replace(" ", "_")
    clean = COMPLETE_TAG.sub("", text).rstrip()
    return clean, mood


class PhotoLibrary:
    def __init__(self, photos_dir: Path, generated_dir: Path, db: Database):
        self.photos_dir = photos_dir
        self.generated_dir = generated_dir
        self.db = db

    def manifest(self) -> dict:
        """Effective manifest: directory scan merged with manifest.json overrides."""
        moods: dict[str, dict] = {}
        if self.photos_dir.is_dir():
            for sub in sorted(self.photos_dir.iterdir()):
                if not sub.is_dir() or sub.name == "reference":
                    continue  # reference/ holds her face refs for SD, not sendable photos
                files = [f.name for f in sorted(sub.iterdir()) if f.suffix.lower() in IMAGE_EXTS]
                if not files:
                    continue
                desc, min_stage = DEFAULT_MOOD_META.get(sub.name, ("a casual photo", "friendly"))
                moods[sub.name] = {"description": desc, "min_stage": min_stage, "files": files}
        override_path = self.photos_dir / "manifest.json"
        if override_path.exists():
            try:
                overrides = json.loads(override_path.read_text()).get("moods", {})
                for mood, o in overrides.items():
                    if mood in moods:
                        moods[mood].update({k: v for k, v in o.items() if k in ("description", "min_stage")})
            except (json.JSONDecodeError, OSError):
                pass
        return {"moods": moods}

    def moods_for_stage(self, stage: str) -> dict[str, str]:
        """mood -> description, filtered to what the stage has unlocked."""
        stage_rank = STAGE_NAMES.index(stage)
        out = {}
        for mood, info in self.manifest()["moods"].items():
            min_stage = info.get("min_stage", "friendly")
            if min_stage in STAGE_NAMES and STAGE_NAMES.index(min_stage) <= stage_rank:
                out[mood] = info["description"]
        return out

    def _pool(self, mood: str) -> list[str]:
        """URL paths for every image available for a mood (pack + generated)."""
        paths = []
        sub = self.photos_dir / mood
        if sub.is_dir():
            paths += [f"photos/{mood}/{f.name}" for f in sorted(sub.iterdir())
                      if f.suffix.lower() in IMAGE_EXTS]
        for row in self.db.query("SELECT filename FROM photos_generated WHERE mood = ?", (mood,)):
            if (self.generated_dir / row["filename"]).exists():
                paths.append(f"generated/{row['filename']}")
        return paths

    def pick(self, mood: str, stage: str) -> str | None:
        """Pick a photo path for a mood, avoiding recent repeats."""
        available = self.moods_for_stage(stage)
        if mood not in available:
            mood = "selfie_generic" if "selfie_generic" in available else next(iter(available), None)
            if mood is None:
                return None
        recent = set(self.db.recent_photo_paths(10))
        pool = self._pool(mood)
        fresh = [p for p in pool if p not in recent]
        candidates = fresh or pool
        if not candidates:
            # fall back to any unlocked mood with images
            for alt in available:
                candidates = [p for p in self._pool(alt) if p not in recent] or self._pool(alt)
                if candidates:
                    break
        return random.choice(candidates) if candidates else None
