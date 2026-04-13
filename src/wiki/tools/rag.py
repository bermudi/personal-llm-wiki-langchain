"""RAG search tool for the wiki agent."""

from __future__ import annotations

from langchain_core.tools import tool

from wiki.rag.chroma_store import retrieve as _retrieve


@tool
def search_wiki(query: str, k: int = 5) -> str:
    """Search the wiki for pages semantically relevant to a query.

    Uses the Chroma vector store to find the most relevant pages by meaning,
    not just keyword match. Use this before answering questions or creating new pages.

    Args:
        query: Natural language question or topic to search for.
        k: Number of results to return. Defaults to 5.
    """
    try:
        docs = _retrieve(query, k=k)
    except Exception as e:
        return f"Error searching wiki: {e}"

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
