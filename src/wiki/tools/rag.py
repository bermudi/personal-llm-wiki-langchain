"""RAG search tool for the wiki agent."""

from __future__ import annotations

from langchain_core.tools import tool

from wiki.rag.chroma_store import retrieve as _retrieve


def _try_obs_context() -> tuple:
    """Try to open the obs store for the current wiki workspace.

    Returns (ObsStore | None, run_id).  If the wiki dir or obs DB can't be
    found, returns (None, "") so the caller can pass-through without obs.
    """
    try:
        from wiki.observability import ObsStore, get_obs_db_path
        import uuid

        db_path = get_obs_db_path()
        if not db_path.exists():
            return None, ""
        store = ObsStore(db_path)
        run_id = uuid.uuid4().hex
        store.insert_run(
            run_id=run_id,
            thread_id=f"search-{run_id[:8]}",
            command="search_wiki",
            model="embeddings",
            reasoning_effort=None,
        )
        return store, run_id
    except Exception:
        return None, ""


@tool
def search_wiki(query: str, k: int = 5) -> str:
    """Search the wiki for pages semantically relevant to a query.

    Uses the Chroma vector store to find the most relevant pages by meaning,
    not just keyword match. Use this before answering questions or creating new pages.

    Args:
        query: Natural language question or topic to search for.
        k: Number of results to return. Defaults to 5.
    """
    store, run_id = _try_obs_context()
    try:
        docs = _retrieve(query, k=k, obs_store=store, run_id=run_id)
    except Exception as e:
        return f"Error searching wiki: {e}"
    finally:
        if store is not None:
            store.close()

    if not docs:
        return "No relevant pages found in the wiki."

    lines = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        title = doc.metadata.get("title", "unknown")
        # Include first 200 chars of content as preview
        preview = doc.page_content[:200].replace("\n", " ")
        lines.append(f"### {title} ({source})\n{preview}...")

    return "\n\n".join(lines)
