"""wiki telegram poll — long-poll Telegram into the wiki agent."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from langchain_core.messages import AIMessage
from rich.console import Console

from wiki.agent import create_wiki_agent, SYSTEM_PROMPT
from wiki.checkpointing import PersistentCheckpointer, get_checkpoint_db_path
from wiki.commands.ingest import SYSTEM_SUFFIX as INGEST_SYSTEM_SUFFIX
from wiki.commands.ingest import build_ingest_prompt
from wiki.config import (
    build_model,
    get_chat_base_url,
    get_model_name,
    get_reasoning_effort,
    get_use_responses_api,
    require_telegram_bot_token,
    validate_wiki_dir,
)
from wiki.middleware.linter import create_linter_middleware
from wiki.observability import create_observability_middleware, init_run
from wiki.slash_commands import SlashCommandContext, build_telegram_slash_registry
from wiki.telegram_client import TelegramApiError, TelegramClient
from wiki.telegram_state import TelegramStateStore, get_telegram_db_path

console = Console()

_TELEGRAM_HELP_FOOTER = (
    "Plain text → chat with the wiki agent.\n"
    "Files (documents, photos) → ingest into the wiki."
)

_TELEGRAM_SLASH_REGISTRY = build_telegram_slash_registry()


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
    caption = message.get("caption") or ""

    # ── File attachments → ingest ─────────────────────────────────
    document = message.get("document")
    photos = message.get("photo")

    if document or photos:
        _handle_attachment(
            message=message,
            document=document,
            photos=photos,
            caption=caption,
            client=client,
            state_store=state_store,
            checkpointer=checkpointer,
            model=model,
            session=session,
        )
        return

    # ── Plain text → chat turn ────────────────────────────────────
    if not isinstance(text, str) or not text.strip():
        reply = "Send a file to ingest, or text to chat."
        client.send_messages(chat_id, reply)
        state_store.record_event(
            session=session,
            role="assistant",
            content=reply,
            telegram_update_id=update.get("update_id"),
            telegram_message_id=message.get("message_id"),
        )
        return

    slash_result = _TELEGRAM_SLASH_REGISTRY.dispatch(
        text,
        SlashCommandContext(
            transport="telegram",
            wiki_dir=Path.cwd(),
            thread_id=session.active_thread_id,
            model_name=get_model_name(),
            chat_base_url=get_chat_base_url(),
            reasoning_effort=get_reasoning_effort(),
            use_responses_api=get_use_responses_api(),
            session_id=session.session_id,
            active_epoch=session.active_epoch,
            help_footer=_TELEGRAM_HELP_FOOTER,
        ),
    )
    if slash_result is not None:
        reply = slash_result.reply
        if slash_result.action == "reset-thread":
            rotated = state_store.rotate_session(chat_id, reason="slash-command")
            reply = (
                f"{reply}\n"
                f"Epoch: {rotated.active_epoch}\n"
                f"Thread: {rotated.active_thread_id}"
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


def _handle_attachment(
    *,
    message: dict,
    document: dict | None,
    photos: list[dict] | None,
    caption: str,
    client: TelegramClient,
    state_store: TelegramStateStore,
    checkpointer: PersistentCheckpointer,
    model: object,
    session,
) -> None:
    """Download file attachment(s) to raw/ and run an ingest turn."""
    chat_id = (message.get("chat") or {}).get("id")
    raw_dir = Path.cwd() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    downloaded_paths: list[str] = []

    try:
        # Document attachment
        if isinstance(document, dict) and "file_id" in document:
            file_id = document["file_id"]
            file_name = document.get("file_name") or f"document_{file_id[:8]}"
            dest = raw_dir / file_name
            client.download_file(file_id, dest)
            downloaded_paths.append(f"raw/{file_name}")

        # Photo attachment — download the largest resolution
        if isinstance(photos, list) and photos:
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            file_id = largest["file_id"]
            # Telegram photo file_ids don't carry original filename — synthesize one
            photo_name = f"photo_{file_id[:8]}.jpg"
            dest = raw_dir / photo_name
            client.download_file(file_id, dest)
            downloaded_paths.append(f"raw/{photo_name}")
    except TelegramApiError as exc:
        client.send_messages(chat_id, f"Failed to download attachment: {exc}")
        return
    except OSError as exc:
        client.send_messages(chat_id, f"Failed to save attachment: {exc}")
        return

    if not downloaded_paths:
        client.send_messages(chat_id, "Couldn't extract any files from that message.")
        return

    client.send_messages(
        chat_id,
        f"📥 Received {len(downloaded_paths)} file(s): {', '.join(p.split('/')[-1] for p in downloaded_paths)}. Ingesting...",
    )

    # Validate all files are text-readable
    valid_paths: list[str] = []
    rejected: list[str] = []
    for path in downloaded_paths:
        try:
            (Path.cwd() / path).read_text(encoding="utf-8")
            valid_paths.append(path)
        except UnicodeDecodeError:
            rejected.append(path)

    if rejected:
        client.send_messages(
            chat_id,
            f"❌ Skipped non-text files: {', '.join(rejected)}. Only text-based files (markdown, txt, csv, etc.) are supported.",
        )
    if not valid_paths:
        return

    # Build ingest prompt covering all valid files
    if len(valid_paths) == 1:
        source_path = valid_paths[0]
        word_count = len((Path.cwd() / source_path).read_text(encoding="utf-8").split())
        prompt = build_ingest_prompt(source_path, word_count)
    else:
        sources_info: list[str] = []
        total_words = 0
        for path in valid_paths:
            content = (Path.cwd() / path).read_text(encoding="utf-8")
            wc = len(content.split())
            sources_info.append(f"- `{path}` ({wc} words)")
            total_words += wc
        prompt = (
            f"Ingest the following source files into the wiki:\n\n"
            + "\n".join(sources_info)
            + f"\n\nTotal: {total_words} words across {len(valid_paths)} files."
            + ("\nSome sources may benefit from the long-source review graph (review_long_source)." if total_words > 10000 else "")
            + "\n\nStart by reading each source and wiki/index.md, then present your plan. "
            "Do NOT make any changes yet — describe what pages you plan to create/update and why."
        )

    if caption.strip():
        prompt += f"\n\nUser notes: {caption.strip()}"

    # Run as ingest turn — inject system suffix + prompt as the initial messages
    response = _run_ingest_turn(
        prompt=prompt,
        thread_id=session.active_thread_id,
        checkpointer=checkpointer,
        model=model,
    )
    client.send_messages(chat_id, response)
    state_store.record_event(
        session=session,
        role="assistant",
        content=response,
        telegram_update_id=message.get("update_id"),
        telegram_message_id=message.get("message_id"),
    )


def _run_ingest_turn(*, prompt: str, thread_id: str, checkpointer: PersistentCheckpointer, model: object) -> str:
    """Run an ingest-mode agent turn with the ingest system suffix appended."""
    combined_system = SYSTEM_PROMPT + INGEST_SYSTEM_SUFFIX

    store, run_id = init_run("telegram-ingest", thread_id)
    obs_middleware = create_observability_middleware(store, run_id)
    agent = create_wiki_agent(
        model=model,
        checkpointer=checkpointer.saver,
        system_prompt=combined_system,
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
        agent.invoke(
            {"messages": [
                {"role": "user", "content": prompt},
            ]},
            config=config,
        )
        state = agent.get_state(config)
        messages = list(state.values.get("messages", []))
        return _latest_ai_text(messages) or "Ingest complete, but I don't have a summary to send back."
    finally:
        store.close()


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
