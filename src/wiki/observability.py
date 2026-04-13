"""Deep observability — logs every model call, tool call, and message to SQLite.

Tables:
    obs_runs        — one row per agent session (chat, ingest, query)
    obs_model_calls — every LLM invocation: messages in, response out, reasoning, tokens
    obs_tool_calls  — every tool invocation: name, args, result, duration
    obs_messages    — every user/assistant/system message in the conversation

All tables are append-only. Query with any SQLite client:

    sqlite3 .wiki/obs.db "SELECT * FROM obs_model_calls ORDER BY ts DESC LIMIT 5"
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware, wrap_tool_call
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS obs_runs (
    id         TEXT PRIMARY KEY,
    thread_id  TEXT,
    command    TEXT,
    model      TEXT,
    reasoning_effort TEXT,
    started_at TEXT
);

CREATE TABLE IF NOT EXISTS obs_model_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    turn            INTEGER,
    system_msg      TEXT,
    messages_in     TEXT,       -- JSON array of {role, content} dicts
    messages_count  INTEGER,
    tools_available TEXT,       -- JSON array of tool names
    response        TEXT,       -- Full response text
    reasoning       TEXT,       -- Reasoning/thinking content (if any)
    tool_calls      TEXT,       -- JSON array of tool call dicts
    usage           TEXT,       -- JSON: input_tokens, output_tokens, etc.
    duration_ms     INTEGER,
    ts              TEXT,
    FOREIGN KEY (run_id) REFERENCES obs_runs(id)
);

CREATE TABLE IF NOT EXISTS obs_tool_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    turn         INTEGER,
    tool_call_id TEXT,
    tool_name    TEXT,
    arguments    TEXT,          -- JSON
    result       TEXT,
    duration_ms  INTEGER,
    ts           TEXT,
    FOREIGN KEY (run_id) REFERENCES obs_runs(id)
);

CREATE TABLE IF NOT EXISTS obs_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    role         TEXT,
    content      TEXT,
    tool_call_id TEXT,
    tool_name    TEXT,
    ts           TEXT,
    FOREIGN KEY (run_id) REFERENCES obs_runs(id)
);
"""


# ---------------------------------------------------------------------------
# Store — thin SQLite wrapper
# ---------------------------------------------------------------------------

class ObsStore:
    """SQLite-backed append-only observability store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()

    def _execute(self, sql: str, params: tuple) -> None:
        """Thread-safe execute + commit."""
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- runs --

    def insert_run(self, *, run_id: str, thread_id: str, command: str, model: str, reasoning_effort: str | None) -> None:
        self._execute(
            "INSERT INTO obs_runs (id, thread_id, command, model, reasoning_effort, started_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, thread_id, command, model, reasoning_effort, self._now()),
        )

    # -- model calls --

    def insert_model_call(
        self,
        *,
        run_id: str,
        turn: int,
        system_msg: str | None,
        messages_in: list[dict],
        tools_available: list[str],
        response: str,
        reasoning: str | None,
        tool_calls: list[dict] | None,
        usage: dict | None,
        duration_ms: int,
    ) -> None:
        self._execute(
            """INSERT INTO obs_model_calls
               (run_id, turn, system_msg, messages_in, messages_count, tools_available,
                response, reasoning, tool_calls, usage, duration_ms, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                turn,
                system_msg,
                json.dumps(messages_in, default=str),
                len(messages_in),
                json.dumps(tools_available),
                response,
                reasoning,
                json.dumps(tool_calls, default=str) if tool_calls else None,
                json.dumps(usage, default=str) if usage else None,
                duration_ms,
                self._now(),
            ),
        )

    # -- tool calls --

    def insert_tool_call(
        self,
        *,
        run_id: str,
        turn: int,
        tool_call_id: str | None,
        tool_name: str,
        arguments: dict,
        result: str,
        duration_ms: int,
    ) -> None:
        self._execute(
            """INSERT INTO obs_tool_calls
               (run_id, turn, tool_call_id, tool_name, arguments, result, duration_ms, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                turn,
                tool_call_id,
                tool_name,
                json.dumps(arguments, default=str),
                result,
                duration_ms,
                self._now(),
            ),
        )

    # -- messages --

    def insert_message(
        self,
        *,
        run_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        self._execute(
            """INSERT INTO obs_messages (run_id, role, content, tool_call_id, tool_name, ts)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, role, content, tool_call_id, tool_name, self._now()),
        )

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_message(msg: AnyMessage) -> dict:
    """Convert a LangChain message to a serializable dict."""
    d: dict[str, Any] = {"role": getattr(msg, "type", "unknown")}
    content = getattr(msg, "content", None)
    d["content"] = content if isinstance(content, str) else json.dumps(content, default=str)
    return d


def _extract_reasoning_from_ai(msg: AIMessage) -> str | None:
    """Extract reasoning/thinking content from an AIMessage."""
    # Check content blocks for reasoning type
    if isinstance(msg.content, list):
        parts: list[str] = []
        for block in msg.content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                if "summary" in block:
                    for s in block["summary"]:
                        if isinstance(s, dict) and s.get("text"):
                            parts.append(s["text"])
        if parts:
            return "".join(parts)

    # Check additional_kwargs (some providers)
    rc = msg.additional_kwargs.get("reasoning_content")
    if rc:
        return str(rc)

    return None


def _extract_tool_calls_from_ai(msg: AIMessage) -> list[dict]:
    """Extract tool calls from an AIMessage."""
    calls = getattr(msg, "tool_calls", None) or []
    return [
        {"name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id")}
        for tc in calls
    ]


# ---------------------------------------------------------------------------
# Middleware factory
# ---------------------------------------------------------------------------

def create_observability_middleware(store: ObsStore, run_id: str) -> list:
    """Create middleware pair: model-call logger + tool-call logger.

    Returns a list suitable for passing to ``create_wiki_agent(middleware=...)``.
    """

    turn_counter = {"value": 0}

    # -- Tool call logging --
    @wrap_tool_call
    def obs_tool_call(request, handler):
        tc = request.tool_call
        tool_name = tc.get("name", "unknown")
        args = tc.get("args", {})
        tc_id = tc.get("id")

        t0 = time.monotonic()
        result = handler(request)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # Truncate huge results to keep the DB manageable
        result_str = str(result)
        if len(result_str) > 50_000:
            result_str = result_str[:50_000] + f"\n... [truncated, {len(result_str)} chars total]"

        store.insert_tool_call(
            run_id=run_id,
            turn=turn_counter["value"],
            tool_call_id=tc_id,
            tool_name=tool_name,
            arguments=args if isinstance(args, dict) else {"__raw": str(args)},
            result=result_str,
            duration_ms=elapsed_ms,
        )
        return result

    # -- Model call logging (via wrap_model_call) --
    class ObsModelMiddleware(AgentMiddleware):
        """Logs every model invocation: full input, full output, reasoning, usage."""

        def wrap_model_call(self, request, handler):
            turn_counter["value"] += 1
            turn = turn_counter["value"]

            # Serialize input
            system_msg = None
            if request.system_message:
                system_msg = str(request.system_message.content)

            messages_in = [_serialize_message(m) for m in request.messages]
            tools_available = [
                getattr(t, "name", str(t)) for t in (request.tools or [])
            ]

            t0 = time.monotonic()
            response = handler(request)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            # Extract response data
            # response is a ModelResponse — get the AIMessage from it
            resp_msg = response.output if hasattr(response, "output") else response

            resp_text = ""
            reasoning = None
            tool_calls = None
            usage = None

            if isinstance(resp_msg, AIMessage):
                content = resp_msg.content
                resp_text = content if isinstance(content, str) else json.dumps(content, default=str)
                reasoning = _extract_reasoning_from_ai(resp_msg)
                tool_calls = _extract_tool_calls_from_ai(resp_msg)
                usage = getattr(resp_msg, "usage_metadata", None)
                if usage and isinstance(usage, dict):
                    pass  # already a dict
                elif usage:
                    usage = vars(usage)

            elif isinstance(resp_msg, str):
                resp_text = resp_msg

            # Log each message in the conversation
            for m in request.messages:
                role = getattr(m, "type", "unknown")
                content_str = ""
                raw_content = getattr(m, "content", "")
                content_str = raw_content if isinstance(raw_content, str) else json.dumps(raw_content, default=str)

                tc_id = None
                tc_name = None
                if isinstance(m, ToolMessage):
                    tc_id = getattr(m, "tool_call_id", None)
                    tc_name = getattr(m, "name", None)

                store.insert_message(
                    run_id=run_id,
                    role=role,
                    content=content_str,
                    tool_call_id=tc_id,
                    tool_name=tc_name,
                )

            # Also log the response as a message
            store.insert_message(
                run_id=run_id,
                role="assistant",
                content=resp_text,
            )

            # Truncate large content for the model_calls table
            if len(resp_text) > 100_000:
                resp_text = resp_text[:100_000] + f"\n... [truncated, full size in obs_messages]"
            if reasoning and len(reasoning) > 100_000:
                reasoning = reasoning[:100_000] + "\n... [truncated]"

            store.insert_model_call(
                run_id=run_id,
                turn=turn,
                system_msg=system_msg[:50_000] if system_msg else None,
                messages_in=messages_in,
                tools_available=tools_available,
                response=resp_text,
                reasoning=reasoning,
                tool_calls=tool_calls,
                usage=usage,
                duration_ms=elapsed_ms,
            )

            return response

    return [ObsModelMiddleware(), obs_tool_call]


# ---------------------------------------------------------------------------
# Convenience — get the obs DB path for a wiki workspace
# ---------------------------------------------------------------------------

def get_obs_db_path(cwd: Path | None = None) -> Path:
    """Return the path to the observability SQLite DB."""
    from wiki.config import validate_wiki_dir
    base = cwd or validate_wiki_dir()
    return base / ".wiki" / "obs.db"


def init_run(command: str, thread_id: str) -> tuple[ObsStore, str]:
    """Create a new run and return (store, run_id).

    Usage::

        store, run_id = init_run("chat", thread_id)
        obs_middleware = create_observability_middleware(store, run_id)
        agent = create_wiki_agent(middleware=[...obs_middleware])
    """
    from wiki.config import get_model_name, get_reasoning_effort

    db_path = get_obs_db_path()
    store = ObsStore(db_path)
    run_id = uuid.uuid4().hex

    store.insert_run(
        run_id=run_id,
        thread_id=thread_id,
        command=command,
        model=get_model_name(),
        reasoning_effort=get_reasoning_effort(),
    )
    return store, run_id
