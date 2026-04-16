"""Wiki agent construction."""

from __future__ import annotations

from langchain.agents import create_agent

from wiki.tools.chunking import review_long_source, split_source
from wiki.tools.filesystem import edit_file, list_files, read_file, search_files, write_file
from wiki.tools.git import git_commit, git_log, git_status
from wiki.tools.rag import search_wiki

SYSTEM_PROMPT = """\
You are a personal wiki agent. You maintain a knowledge base stored as markdown files in the current directory.

## Architecture

The wiki has three layers:
- `raw/` — Immutable source documents (human-owned, never modify these)
- `wiki/` — Knowledge pages you create and maintain (pages, index.md, log.md)
- `scratch/` — Transient working artifacts from chunking (temporary, can be cleaned up)

## Git Convention

- Always check `git_status` before modifying wiki files. Uncommitted changes are human edits — they are authoritative. Integrate your work around them.
- Write/edit tools automatically stage changed files. Call `git_commit` when an operation is complete to seal the commit. Commits only include files you wrote — nothing else gets swept in.
- Commit messages follow the pattern: `<operation>: <description>`
- Operations: ingest, query, lint, schema, bootstrap

## Page Filing

- Create pages in `wiki/` with descriptive kebab-case names (e.g., `wiki/institutional-trust.md`)
- Each page should be self-contained: title, context, content, source references
- Update `wiki/index.md` when creating or significantly updating a page — add entry under the appropriate category with link and one-line summary
- Append to `wiki/log.md` with format: `## [YYYY-MM-DD] <operation> | <description>` followed by bullet points
- Use `search_wiki` to find relevant existing pages before creating new ones

## Long-source pipeline (automatic)

For sources over ~70k words (~100k tokens), the ingest command runs the chunk-review pipeline BEFORE the agent session starts. The pipeline produces:
1. Chunk summaries and review artifacts in `scratch/<source>/chunk-review/`
2. Draft wiki pages in `scratch/<source>/chunk-review/attempt-XX/drafts/`

You will receive the pipeline results in your initial prompt. Read the draft files and review.json, then decide which pages to create/update.

For shorter sources, read the source in full and process directly (no chunking needed).

## Orient Yourself

Before each operation, read `wiki/index.md` to understand what exists. \
This keeps you grounded in the current state of the wiki.
"""


def get_all_tools() -> list:
    """Return the full tool inventory for the wiki agent."""
    return [
        # Filesystem
        read_file,
        write_file,
        edit_file,
        list_files,
        search_files,
        # Git
        git_status,
        git_commit,
        git_log,
        # RAG
        search_wiki,
        # Long-source review
        split_source,
        review_long_source,
    ]


def create_wiki_agent(
    *,
    model: object | None = None,
    extra_tools: list | None = None,
    checkpointer: object | None = None,
    middleware: list | None = None,
    system_prompt: str | None = None,
):
    """Create a wiki agent with all standard tools.

    Args:
        model: ChatOpenAI instance. If None, built from config.
        extra_tools: Additional tools beyond the standard set.
        checkpointer: Optional checkpointer for HITL / chat persistence.
        middleware: Optional middleware list (e.g., linter, HITL).
    """
    if model is None:
        from wiki.config import build_model

        model = build_model()

    tools = get_all_tools()
    if extra_tools:
        tools.extend(extra_tools)

    kwargs: dict = {
        "model": model,
        "tools": tools,
        "system_prompt": system_prompt or SYSTEM_PROMPT,
    }

    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if middleware is not None:
        kwargs["middleware"] = middleware

    return create_agent(**kwargs)
