"""Personal LLM Wiki — CLI entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="wiki",
    help="Personal LLM wiki powered by LangChain.",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Create a new wiki workspace in the current directory."""
    from wiki.commands.init import run_init

    run_init()


@app.command()
def ingest(
    path: str = typer.Argument(help="Path to raw source file to ingest"),
) -> None:
    """Ingest a raw source file into the wiki (interactive REPL)."""
    from wiki.commands.ingest import run_ingest

    run_ingest(path)


@app.command()
def query(
    question: str = typer.Argument(help="Question to ask the wiki"),
) -> None:
    """Ask a one-shot question against the wiki."""
    from wiki.commands.query import run_query

    run_query(question)


@app.command()
def chat() -> None:
    """Open an interactive chat session with the wiki."""
    from wiki.commands.chat import run_chat

    run_chat()


@app.command()
def reindex() -> None:
    """Rebuild the Chroma vector store from all wiki pages."""
    from wiki.commands.reindex import run_reindex

    run_reindex()


if __name__ == "__main__":
    app()
