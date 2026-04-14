"""Personal LLM Wiki — CLI entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="wiki",
    help="Personal LLM wiki powered by LangChain.",
    no_args_is_help=True,
)

telegram_app = typer.Typer(
    help="Telegram transport for the wiki agent.",
    no_args_is_help=True,
)
app.add_typer(telegram_app, name="telegram")


@app.command()
def init() -> None:
    """Create a new wiki workspace in the current directory."""
    from wiki.commands.init import run_init

    run_init()


@app.command()
def ingest(
    path: str = typer.Argument(help="Path to raw source file to ingest"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Use plain text mode instead of TUI"),
) -> None:
    """Ingest a raw source file into the wiki (interactive REPL)."""
    from wiki.commands.ingest import run_ingest

    run_ingest(path, no_tui=no_tui)


@app.command()
def query(
    question: str = typer.Argument(help="Question to ask the wiki"),
) -> None:
    """Ask a one-shot question against the wiki."""
    from wiki.commands.query import run_query

    run_query(question)


@app.command()
def chat(
    no_tui: bool = typer.Option(False, "--no-tui", help="Use plain text mode instead of TUI"),
) -> None:
    """Open an interactive chat session with the wiki."""
    from wiki.commands.chat import run_chat

    run_chat(no_tui=no_tui)


@app.command()
def reindex() -> None:
    """Rebuild the Chroma vector store from all wiki pages."""
    from wiki.commands.reindex import run_reindex

    run_reindex()


@telegram_app.command("poll")
def telegram_poll(
    once: bool = typer.Option(False, "--once", help="Process a single polling batch and exit."),
    timeout: int = typer.Option(30, min=1, max=50, help="Telegram long-poll timeout in seconds."),
) -> None:
    """Long-poll Telegram and route private chat messages into the wiki agent."""
    from wiki.commands.telegram import run_poll

    run_poll(once=once, timeout=timeout)


if __name__ == "__main__":
    app()
