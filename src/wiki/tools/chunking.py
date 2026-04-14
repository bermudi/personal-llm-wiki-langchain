"""Chunking tools for long source documents."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from wiki.chunking_core import load_source_chunks
from wiki.ingest_graph import run_chunk_review_graph


@tool
def split_source(path: str, chunk_size: int = 5000) -> str:
    """Split a long source document into raw chunks.

    Auto-detects structural sections (chapters, headings, stanzas).
    If sections are found, each section becomes its own chunk unless it is still
    too large, in which case it is split again at paragraph boundaries.

    Each chunk is saved as a separate file in ``scratch/<source-slug>/chunk-NNN.md``.
    This is a mechanical inspection tool — it does not call an LLM.

    Args:
        path: Path to the source file in raw/.
        chunk_size: Target word count per chunk. Defaults to 5000.
    """
    try:
        source_path, chunks, method, total_words = load_source_chunks(path, chunk_size)
    except FileNotFoundError:
        return f"Error: Source file not found: {path}"

    if total_words <= chunk_size:
        return f"Source is only {total_words} words — no chunking needed. Process directly."

    chunk_dir = Path.cwd() / "scratch" / source_path.stem
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_paths: list[str] = []
    for chunk in chunks:
        chunk_path = chunk_dir / f"{chunk.chunk_id}.md"
        chunk_path.write_text(chunk.text, encoding="utf-8")
        chunk_paths.append(f"scratch/{source_path.stem}/{chunk.chunk_id}.md")

    return (
        f"Split {total_words} words into {len(chunks)} chunks ({method}):\n"
        + "\n".join(chunk_paths)
    )


@tool
def review_long_source(path: str, chunk_size: int = 1500, max_retries: int = 1) -> str:
    """Run the long-source chunk review graph and prepare page drafts.

    This workflow:
    1. Splits the source into raw chunks
    2. Creates embeddings for those chunks
    3. Summarizes each chunk
    4. Builds candidate groups from embedding neighborhoods
    5. Lets an LLM review the grouping and optionally retry with a smaller chunk size
    6. Writes page drafts to ``scratch/<source-slug>/chunk-review/attempt-XX/drafts/``

    It is the preferred tool for long sources (~10k+ words) because it uses
    embeddings + summaries to decide which chunks belong together before synthesis.

    Args:
        path: Path to the source file in raw/.
        chunk_size: Initial target chunk size. Defaults to 1500.
        max_retries: Maximum number of re-splitting retries. Defaults to 1.
    """
    try:
        from wiki.observability import get_obs_db_path, ObsStore

        db_path = get_obs_db_path()
        obs_store = ObsStore(db_path)
    except (SystemExit, Exception):
        obs_store = None

    try:
        result = run_chunk_review_graph(
            path=path,
            chunk_size=chunk_size,
            max_retries=max_retries,
            obs_store=obs_store,
        )
    except FileNotFoundError:
        return f"Error: Source file not found: {path}"
    finally:
        if obs_store is not None:
            obs_store.close()

    notes = "\n".join(f"- {note}" for note in result.review_notes) or "- No review notes"
    drafts = "\n".join(f"- {draft_path}" for draft_path in result.draft_paths) or "- No drafts generated"
    titles = ", ".join(result.group_titles) or "none"
    return (
        f"Reviewed long source `{result.source_path}` in {result.attempt} attempt(s).\n"
        f"Final chunk size: {result.final_chunk_size} words\n"
        f"Chunks: {result.chunk_count}\n"
        f"Decision: {result.decision}\n"
        f"Draft groups: {titles}\n"
        f"Artifacts: {result.artifact_dir}\n"
        f"Review notes:\n{notes}\n"
        f"Draft files:\n{drafts}"
    )
