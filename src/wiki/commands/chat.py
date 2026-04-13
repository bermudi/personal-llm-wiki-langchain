"""wiki chat — interactive REPL."""

from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.markdown import Markdown

from wiki.agent import create_wiki_agent
from wiki.config import validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware

console = Console()


def run_chat() -> None:
    cwd = validate_wiki_dir()

    thread_id = str(uuid.uuid4())
    checkpointer = MemorySaver()

    agent = create_wiki_agent(
        checkpointer=checkpointer,
        middleware=[create_linter_middleware()],
    )

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,
    }

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

        console.print("[dim]Thinking...[/dim]")
        result = agent.invoke({"messages": messages}, config=config)
        messages = result["messages"]

        # The last message is the assistant's response
        # Find the last AI message (skip tool messages)
        response_text = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and hasattr(msg, "type") and msg.type == "ai":
                response_text = msg.content
                break

        console.print(Markdown(response_text))
        console.print()
