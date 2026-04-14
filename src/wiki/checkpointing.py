"""Persistent LangGraph checkpointer helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def get_checkpoint_db_path(cwd: Path | None = None) -> Path:
    """Return the path to the persistent LangGraph checkpoint DB."""
    from wiki.config import validate_wiki_dir

    base = cwd or validate_wiki_dir()
    return base / ".wiki" / "checkpoints.sqlite"


class PersistentCheckpointer:
    """SQLite-backed LangGraph checkpointer for durable thread state."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        self.saver = SqliteSaver(self._conn)
        self.saver.setup()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PersistentCheckpointer:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
