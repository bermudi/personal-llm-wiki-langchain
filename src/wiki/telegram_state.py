"""Persistent Telegram session and recall storage."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_cursors (
    bot_id          TEXT PRIMARY KEY,
    last_update_id  INTEGER NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_sessions (
    session_id       TEXT PRIMARY KEY,
    chat_id          INTEGER NOT NULL UNIQUE,
    chat_type        TEXT NOT NULL,
    user_id          INTEGER,
    active_epoch     INTEGER NOT NULL,
    active_thread_id TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    last_active_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_epochs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    epoch        INTEGER NOT NULL,
    thread_id    TEXT NOT NULL UNIQUE,
    summary      TEXT,
    created_at   TEXT NOT NULL,
    closed_at    TEXT,
    close_reason TEXT,
    UNIQUE(session_id, epoch)
);

CREATE TABLE IF NOT EXISTS telegram_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL,
    epoch               INTEGER NOT NULL,
    thread_id           TEXT NOT NULL,
    telegram_update_id  INTEGER,
    telegram_message_id INTEGER,
    role                TEXT NOT NULL,
    content             TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
"""


@dataclass(slots=True)
class TelegramSession:
    session_id: str
    chat_id: int
    chat_type: str
    user_id: int | None
    active_epoch: int
    active_thread_id: str


def get_telegram_db_path(cwd: Path | None = None) -> Path:
    """Return the path to the Telegram state DB."""
    from wiki.config import validate_wiki_dir

    base = cwd or validate_wiki_dir()
    return base / ".wiki" / "telegram.db"


class TelegramStateStore:
    """SQLite-backed transport/session state for Telegram."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()

    def close(self) -> None:
        self._conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def get_cursor(self, bot_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT last_update_id FROM telegram_cursors WHERE bot_id = ?",
            (bot_id,),
        ).fetchone()
        return int(row[0]) if row else None

    def set_cursor(self, bot_id: str, last_update_id: int) -> None:
        self._execute(
            """INSERT INTO telegram_cursors (bot_id, last_update_id, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(bot_id)
               DO UPDATE SET last_update_id = excluded.last_update_id,
                             updated_at = excluded.updated_at""",
            (bot_id, last_update_id, self._now()),
        )

    def get_or_create_session(self, *, chat_id: int, chat_type: str, user_id: int | None) -> TelegramSession:
        row = self._conn.execute(
            """SELECT session_id, chat_id, chat_type, user_id, active_epoch, active_thread_id
               FROM telegram_sessions WHERE chat_id = ?""",
            (chat_id,),
        ).fetchone()
        if row:
            next_user_id = user_id if user_id is not None else row[3]
            self._execute(
                "UPDATE telegram_sessions SET last_active_at = ?, user_id = ? WHERE chat_id = ?",
                (self._now(), next_user_id, chat_id),
            )
            return TelegramSession(row[0], row[1], row[2], next_user_id, row[4], row[5])

        now = self._now()
        session_id = f"telegram-{chat_type}-{chat_id}"
        thread_id = self._thread_id(chat_id, 1)

        self._execute(
            """INSERT INTO telegram_sessions
               (session_id, chat_id, chat_type, user_id, active_epoch, active_thread_id, created_at, last_active_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, chat_id, chat_type, user_id, 1, thread_id, now, now),
        )
        self._execute(
            "INSERT INTO telegram_epochs (session_id, epoch, thread_id, created_at) VALUES (?, ?, ?, ?)",
            (session_id, 1, thread_id, now),
        )
        return TelegramSession(session_id, chat_id, chat_type, user_id, 1, thread_id)

    def rotate_session(self, chat_id: int, *, reason: str) -> TelegramSession:
        row = self._conn.execute(
            """SELECT session_id, chat_id, chat_type, user_id, active_epoch, active_thread_id
               FROM telegram_sessions WHERE chat_id = ?""",
            (chat_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No session for chat {chat_id}")

        session = TelegramSession(row[0], row[1], row[2], row[3], row[4], row[5])
        next_epoch = session.active_epoch + 1
        now = self._now()
        thread_id = self._thread_id(chat_id, next_epoch)

        self._execute(
            """UPDATE telegram_epochs
               SET closed_at = ?, close_reason = ?
               WHERE session_id = ? AND epoch = ?""",
            (now, reason, session.session_id, session.active_epoch),
        )
        self._execute(
            "INSERT INTO telegram_epochs (session_id, epoch, thread_id, created_at) VALUES (?, ?, ?, ?)",
            (session.session_id, next_epoch, thread_id, now),
        )
        self._execute(
            """UPDATE telegram_sessions
               SET active_epoch = ?, active_thread_id = ?, last_active_at = ?
               WHERE session_id = ?""",
            (next_epoch, thread_id, now, session.session_id),
        )
        return TelegramSession(
            session.session_id,
            session.chat_id,
            session.chat_type,
            session.user_id,
            next_epoch,
            thread_id,
        )

    def record_event(
        self,
        *,
        session: TelegramSession,
        role: str,
        content: str,
        telegram_update_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        timestamp = self._now()
        self._execute(
            """INSERT INTO telegram_events
               (session_id, epoch, thread_id, telegram_update_id, telegram_message_id, role, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.session_id,
                session.active_epoch,
                session.active_thread_id,
                telegram_update_id,
                telegram_message_id,
                role,
                content,
                timestamp,
            ),
        )
        self._execute(
            "UPDATE telegram_sessions SET last_active_at = ? WHERE session_id = ?",
            (timestamp, session.session_id),
        )

    def _thread_id(self, chat_id: int, epoch: int) -> str:
        return f"telegram:{chat_id}:epoch:{epoch}"
