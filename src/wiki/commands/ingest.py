"""wiki ingest — conversational ingest REPL with streaming and observability."""

from __future__ import annotations

import uuid
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.panel import Panel

from wiki.agent import SYSTEM_PROMPT, create_wiki_agent
from wiki.config import get_model_name, get_wiki_root, validate_wiki_dir
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


LONG_SOURCE_WORD_THRESHOLD = 70_000  # ~100k tokens


def build_ingest_prompt(path: str, word_count: int) -> str:
    """Build a short-source ingest prompt by reading the file from disk."""
    content = (get_wiki_root() / path).read_text(encoding="utf-8")
    return _build_short_prompt(path, content, word_count)


def _build_short_prompt(path: str, content: str, word_count: int) -> str:
    """Prompt for sources that fit in a single context window."""
    return (
        f"Ingest the source file at `{path}` into the wiki.\n\n"
        f"The source is {word_count} words — short enough to process directly. "
        "Create wiki pages from this source.\n\n"
        f"## Source: {path}\n\n{content}\n\n"
        "Read wiki/index.md, then present your plan. "
        "Do NOT make any changes yet — describe what pages you plan to create/update and why."
    )


def _build_long_prompt(path: str, result: object) -> str:
    """Prompt for pre-processed long sources, with pipeline results and draft content injected."""
    notes = "\n".join(f"- {n}" for n in result.review_notes) or "- No review notes"
    titles = ", ".join(result.group_titles) or "none"

    # Inject draft file contents directly so the agent doesn't have to discover them
    draft_sections: list[str] = []
    for draft_path in result.draft_paths:
        p = Path(draft_path)
        if p.exists():
            draft_sections.append(f"### {p.stem}\n\n{p.read_text(encoding='utf-8')}")
        else:
            draft_sections.append(f"### {p.stem}\n\n[Draft file not found: {draft_path}]")
    drafts_text = "\n\n".join(draft_sections) if draft_sections else "No draft files generated."

    # Also inject the review JSON for grouping rationale
    review_path = Path(result.artifact_dir) / "review.json"
    review_text = ""
    if review_path.exists():
        review_text = f"\n## Review Decisions\n\n{review_path.read_text(encoding='utf-8')}\n"

    return (
        f"Ingest the source file at `{path}` into the wiki.\n\n"
        f"The source was too large for a single pass, so it was pre-processed through the chunk-review pipeline.\n"
        f"Pipeline summary:\n"
        f"- Chunks: {result.chunk_count}\n"
        f"- Review decision: {result.decision}\n"
        f"- Draft groups: {titles}\n"
        f"- Artifacts dir: {result.artifact_dir}\n"
        f"Review notes:\n{notes}\n\n"
        f"## Draft Pages\n\n"
        f"The following page drafts were generated. Use these as starting points for your final wiki pages:\n\n"
        f"{drafts_text}\n"
        f"{review_text}\n"
        "Read wiki/index.md, then present your plan for turning these drafts into final wiki pages. "
        "Do NOT make any changes yet — describe what pages you plan to create/update and why."
    )


# Shortcut map for ingest approval phrases
_INGEST_SHORTCUTS = {
    phrase: "Plan approved. Proceed with the full ingestion now — create pages, update index.md, append to log.md, and commit."
    for phrase in ("go", "ok", "approve", "yes", "do it", "proceed", "looks good")
}


def run_ingest(path: str, *, no_tui: bool = False) -> None:
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

    # ── Run pipeline for long sources BEFORE the agent loop ──────────
    pipeline_result = None
    if word_count > LONG_SOURCE_WORD_THRESHOLD:
        console.print(Panel(
            f"Source is [bold]{word_count:,}[/bold] words — running chunk-review pipeline…",
            title="Pre-processing",
            border_style="yellow",
        ))
        from wiki.ingest_graph import run_chunk_review_graph
        pipeline_result = run_chunk_review_graph(
            path=path,
            obs_store=store,
            run_id=run_id,
        )
        draft_paths = "\n".join(f"  {p}" for p in pipeline_result.draft_paths)
        console.print(Panel(
            f"Pipeline complete.\n"
            f"Chunks: {pipeline_result.chunk_count}\n"
            f"Decision: {pipeline_result.decision}\n"
            f"Draft groups: {', '.join(pipeline_result.group_titles)}\n"
            f"Draft files:\n{draft_paths}",
            title="Pipeline Results",
            border_style="green",
        ))

    # Build initial prompt based on whether pipeline ran
    if pipeline_result is not None:
        user_prompt = _build_long_prompt(path, pipeline_result)
    else:
        user_prompt = _build_short_prompt(path, source_content, word_count)

    # Build agent — the REPL *is* the approval gate
    checkpointer = MemorySaver()
    agent = create_wiki_agent(
        checkpointer=checkpointer,
        system_prompt=SYSTEM_PROMPT + SYSTEM_SUFFIX,
        middleware=[
            create_linter_middleware(),
            *obs_middleware,
        ],
    )

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 100,
    }

    initial_messages: list[dict] = [
        {"role": "user", "content": user_prompt},
    ]

    try:
        if not no_tui:
            from wiki.tui import run_tui_ingest

            run_tui_ingest(
                agent,
                config,
                initial_messages,
                model_name=get_model_name(),
                shortcuts=_INGEST_SHORTCUTS,
            )
            return

        # ── Plain fallback ──────────────────────────────────────────
        console.print(Panel(
            f"Ingesting [bold]{path}[/bold] ({word_count} words)",
            title="Wiki Ingest",
            border_style="cyan",
        ))
        console.print("The agent will present a plan first. Discuss, redirect, or approve.\n")

        event_stream = agent.stream(
            {"messages": initial_messages},
            config=config,
            stream_mode="messages",
        )
        stream_agent_response(event_stream)
        console.print()

        # REPL loop — only pass NEW messages; the checkpointer owns history
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

            event_stream = agent.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
                stream_mode="messages",
            )
            stream_agent_response(event_stream)
            console.print()
    finally:
        store.close()
