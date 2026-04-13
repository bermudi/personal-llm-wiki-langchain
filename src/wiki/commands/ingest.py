"""wiki ingest — conversational ingest REPL with streaming and observability."""

from __future__ import annotations

import uuid
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.panel import Panel

from wiki.agent import create_wiki_agent
from wiki.config import validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware
from wiki.observability import create_observability_middleware, init_run
from wiki.streaming import stream_agent_response

console = Console()

SYSTEM_SUFFIX = """\

## Ingest Mode

You are in ingest mode. The user has given you a source file to process into wiki pages.

Behavior:
- Present your plan first: what pages you'll create/update, what the index changes look like.
- Wait for the user to respond before making changes. They may redirect, skip sections, or ask you to merge differently.
- Once the user approves, execute the full pipeline (create pages, update index.md, append to log.md, commit).
- The user is your approval gate — treat every response as a potential course correction.
"""


def _build_ingest_prompt(path: str, word_count: int) -> str:
    return f"""Ingest the source file at `{path}` into the wiki.

The source is {word_count} words long. {'It is long enough to benefit from chunking (use split_source first).' if word_count > 10000 else 'Process it directly without chunking.'}

Start by reading the source and wiki/index.md, then present your plan. Do NOT make any changes yet — describe what pages you plan to create/update and why."""


def run_ingest(path: str) -> None:
    cwd = validate_wiki_dir()

    source_path = Path(path)
    if not source_path.exists():
        source_path = cwd / path
    if not source_path.exists():
        console.print(f"[red]Error: Source file not found: {path}[/red]")
        raise SystemExit(1)

    source_content = source_path.read_text(encoding="utf-8")
    word_count = len(source_content.split())

    thread_id = f"ingest-{source_path.stem}-{uuid.uuid4().hex[:8]}"

    # Observability
    store, run_id = init_run("ingest", thread_id)
    obs_middleware = create_observability_middleware(store, run_id)

    # Build agent — the REPL *is* the approval gate
    checkpointer = MemorySaver()
    agent = create_wiki_agent(
        checkpointer=checkpointer,
        middleware=[
            create_linter_middleware(),
            *obs_middleware,
        ],
    )

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 100,
    }

    console.print(Panel(
        f"Ingesting [bold]{path}[/bold] ({word_count} words)",
        title="Wiki Ingest",
        border_style="cyan",
    ))
    console.print("The agent will present a plan first. Discuss, redirect, or approve.\n")

    # Kick off with the system suffix and ingest prompt
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_SUFFIX},
        {"role": "user", "content": _build_ingest_prompt(path, word_count)},
    ]

    try:
        event_stream = agent.stream(
            {"messages": messages},
            config=config,
            stream_mode="messages",
        )
        stream_agent_response(event_stream)

        # Reconstruct from state
        state = agent.get_state(config)
        messages = list(state.values.get("messages", []))
        console.print()

        # REPL loop
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Ingest session ended.[/dim]")
                break

            if user_input.lower() in ("exit", "quit", "done"):
                console.print("[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            # Shortcuts for common approval phrases
            if user_input.lower() in ("go", "ok", "approve", "yes", "do it", "proceed", "looks good"):
                user_input = "Plan approved. Proceed with the full ingestion now — create pages, update index.md, append to log.md, and commit."

            messages.append({"role": "user", "content": user_input})

            event_stream = agent.stream(
                {"messages": messages},
                config=config,
                stream_mode="messages",
            )
            stream_agent_response(event_stream)

            # Reconstruct from state
            state = agent.get_state(config)
            messages = list(state.values.get("messages", []))
            console.print()
    finally:
        store.close()
