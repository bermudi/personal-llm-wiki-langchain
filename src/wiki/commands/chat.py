"""wiki chat — interactive REPL with streaming and observability."""

from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console

from wiki.agent import create_wiki_agent
from wiki.config import get_model_name, validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware
from wiki.observability import create_observability_middleware, init_run
from wiki.streaming import stream_agent_response

console = Console()


def run_chat(*, no_tui: bool = False) -> None:
    cwd = validate_wiki_dir()

    thread_id = str(uuid.uuid4())

    # Observability
    store, run_id = init_run("chat", thread_id)
    obs_middleware = create_observability_middleware(store, run_id)

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

    try:
        if not no_tui:
            from wiki.tui import run_tui_chat

            run_tui_chat(agent, config, model_name=get_model_name())
            return

        # ── Plain fallback ──────────────────────────────────────────
        console.print("[bold cyan]Wiki Chat[/bold cyan]")
        console.print("Ask questions about your wiki. Type [bold]exit[/bold] or press [bold]Ctrl-D[/bold] to quit.\n")

        messages: list[dict] = []

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if user_input.lower() in ("exit", "quit"):
                console.print("[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            event_stream = agent.stream(
                {"messages": messages},
                config=config,
                stream_mode="messages",
            )
            stream_agent_response(event_stream)

            # Reconstruct messages from latest agent state
            state = agent.get_state(config)
            messages = list(state.values.get("messages", []))
            console.print()
    finally:
        store.close()
