"""wiki telegram poll — long-poll Telegram into the wiki agent."""

from __future__ import annotations

import hashlib
import time

from langchain_core.messages import AIMessage
from rich.console import Console

from wiki.agent import create_wiki_agent
from wiki.checkpointing import PersistentCheckpointer, get_checkpoint_db_path
from wiki.config import build_model, require_telegram_bot_token, validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware
from wiki.observability import create_observability_middleware, init_run
from wiki.telegram_client import TelegramApiError, TelegramClient
from wiki.telegram_state import TelegramStateStore, get_telegram_db_path

console = Console()

_HELP_TEXT = """Wiki Telegram bridge is live.

Commands:
/help   Show this message
/status Show the active session + epoch
/new    Start a fresh epoch without deleting old history
/reset  Alias for /new

Plain text messages are sent to the wiki agent. Private chats only for now."""


def run_poll(*, once: bool = False, timeout: int = 30) -> None:
    validate_wiki_dir()

    token = require_telegram_bot_token()
    bot_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    client = TelegramClient(token)
    state_store = TelegramStateStore(get_telegram_db_path())
    model = build_model()
    checkpointer = PersistentCheckpointer(get_checkpoint_db_path())

    client.delete_webhook(drop_pending_updates=False)
    console.print("[bold cyan]Telegram polling started[/bold cyan]")

    try:
        while True:
            offset = state_store.get_cursor(bot_id)

            try:
                updates = client.get_updates(
                    offset=None if offset is None else offset + 1,
                    timeout=timeout,
                    allowed_updates=["message"],
                )
            except TelegramApiError as exc:
                console.print(f"[red]Polling failed:[/red] {exc}")
                if once:
                    raise SystemExit(1) from exc
                time.sleep(5)
                continue

            if not updates:
                if once:
                    break
                continue

            for update in updates:
                update_id = int(update.get("update_id", 0))
                try:
                    _handle_update(update, client, state_store, checkpointer, model)
                except Exception as exc:  # pragma: no cover - defensive transport guard
                    console.print(f"[red]Failed to process update {update_id}:[/red] {exc}")
                    _send_processing_error(update, client)
                finally:
                    state_store.set_cursor(bot_id, update_id)

            if once:
                break
    finally:
        checkpointer.close()
        state_store.close()


def _handle_update(
    update: dict,
    client: TelegramClient,
    state_store: TelegramStateStore,
    checkpointer: PersistentCheckpointer,
    model: object,
) -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    if not isinstance(chat_id, int) or not isinstance(chat_type, str):
        return

    if chat_type != "private":
        client.send_messages(chat_id, "Private chats only for now.")
        return

    sender = message.get("from") or {}
    user_id = sender.get("id") if isinstance(sender.get("id"), int) else None
    session = state_store.get_or_create_session(chat_id=chat_id, chat_type=chat_type, user_id=user_id)

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        reply = "Send plain text for now — photos, voice notes, and files can wait their turn."
        client.send_messages(chat_id, reply)
        state_store.record_event(
            session=session,
            role="assistant",
            content=reply,
            telegram_update_id=update.get("update_id"),
            telegram_message_id=message.get("message_id"),
        )
        return

    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
    if command in {"/start", "/help"}:
        client.send_messages(chat_id, _HELP_TEXT)
        return
    if command in {"/new", "/reset"}:
        rotated = state_store.rotate_session(chat_id, reason="manual-reset")
        reply = f"Started fresh epoch {rotated.active_epoch}. Old history is still archived; new turns use {rotated.active_thread_id}."
        client.send_messages(chat_id, reply)
        return
    if command == "/status":
        reply = (
            f"Session: {session.session_id}\n"
            f"Epoch: {session.active_epoch}\n"
            f"Thread: {session.active_thread_id}"
        )
        client.send_messages(chat_id, reply)
        return

    state_store.record_event(
        session=session,
        role="user",
        content=text,
        telegram_update_id=update.get("update_id"),
        telegram_message_id=message.get("message_id"),
    )

    response = _run_agent_turn(
        prompt=text,
        thread_id=session.active_thread_id,
        checkpointer=checkpointer,
        model=model,
    )
    client.send_messages(chat_id, response)
    state_store.record_event(
        session=session,
        role="assistant",
        content=response,
        telegram_update_id=update.get("update_id"),
        telegram_message_id=message.get("message_id"),
    )


def _run_agent_turn(*, prompt: str, thread_id: str, checkpointer: PersistentCheckpointer, model: object) -> str:
    store, run_id = init_run("telegram", thread_id)
    obs_middleware = create_observability_middleware(store, run_id)
    agent = create_wiki_agent(
        model=model,
        checkpointer=checkpointer.saver,
        middleware=[
            create_linter_middleware(),
            *obs_middleware,
        ],
    )
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 100,
    }

    try:
        agent.invoke({"messages": [{"role": "user", "content": prompt}]}, config=config)
        state = agent.get_state(config)
        messages = list(state.values.get("messages", []))
        return _latest_ai_text(messages) or "I finished the turn, but I don't have a text reply to send back."
    finally:
        store.close()


def _latest_ai_text(messages: list[object]) -> str | None:
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        text = _extract_text_content(message.content)
        if text:
            return text
    return None


def _extract_text_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
    return "".join(parts).strip()


def _send_processing_error(update: dict, client: TelegramClient) -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return
    try:
        client.send_messages(chat_id, "Something broke on my side while processing that turn. Please retry.")
    except TelegramApiError:
        return
