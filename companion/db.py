"""SQLite access layer.

One shared connection in WAL mode guarded by a lock — plenty for a
single-user local app. All persistent state (settings included) lives in this
one database file so export/wipe stay trivial.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now_ms() -> int:
    return int(time.time() * 1000)


class Database:
    def __init__(self, path: Path | str):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._conn:
            for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
                self._conn.executescript(script.read_text())

    def close(self) -> None:
        self._conn.close()

    # -- generic helpers ---------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run a write statement; returns lastrowid."""
        with self._lock, self._conn:
            cur = self._conn.execute(sql, params)
            return cur.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # -- app_state (JSON key/value) ----------------------------------------

    def get_state(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM app_state WHERE key = ?", (key,))
        if row is None:
            return default
        return json.loads(row["value"])

    def set_state(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    def delete_state(self, key: str) -> None:
        self.execute("DELETE FROM app_state WHERE key = ?", (key,))

    # -- messages ------------------------------------------------------------

    def add_message(self, role: str, content: str, *, photo_path: str | None = None,
                    photo_kind: str | None = None, is_proactive: bool = False,
                    created_at: int | None = None, meta: dict | None = None) -> int:
        return self.execute(
            "INSERT INTO messages (role, content, photo_path, photo_kind, is_proactive, created_at, meta) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (role, content, photo_path, photo_kind, 1 if is_proactive else 0,
             created_at if created_at is not None else now_ms(),
             json.dumps(meta) if meta else None),
        )

    def get_messages(self, *, before_id: int | None = None, limit: int = 50) -> list[dict]:
        """Newest-last page of messages (for the chat view)."""
        if before_id is not None:
            rows = self.query(
                "SELECT * FROM messages WHERE id < ? ORDER BY id DESC LIMIT ?",
                (before_id, limit),
            )
        else:
            rows = self.query("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,))
        rows.reverse()
        for r in rows:
            r["meta"] = json.loads(r["meta"]) if r["meta"] else {}
        return rows

    def recent_photo_paths(self, n: int = 10) -> list[str]:
        rows = self.query(
            "SELECT photo_path FROM messages WHERE photo_path IS NOT NULL AND role = 'companion' "
            "ORDER BY id DESC LIMIT ?", (n,))
        return [r["photo_path"] for r in rows]
