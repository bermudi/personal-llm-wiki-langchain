"""Chroma vector store for semantic wiki page discovery."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from wiki.config import build_embeddings, get_wiki_root

if TYPE_CHECKING:
    from wiki.observability import ObservableEmbeddings, ObsStore


def _get_embeddings(obs_store: ObsStore | None = None, run_id: str = "") -> OpenAIEmbeddings | ObservableEmbeddings:
    """Create embeddings instance using the embedding provider.

    When *obs_store* is provided, returns an ``ObservableEmbeddings`` wrapper
    that logs every ``embed_documents`` / ``embed_query`` call to SQLite.
    """
    inner = build_embeddings()
    if obs_store is not None:
        from wiki.observability import ObservableEmbeddings
        return ObservableEmbeddings(inner, obs_store=obs_store, run_id=run_id)
    return inner


def _chroma_dir() -> Path:
    """Path to the Chroma persistence directory."""
    return get_wiki_root() / "wiki" / ".chroma"


_store_cache: Chroma | None = None


def init_store(*, obs_store: ObsStore | None = None, run_id: str = "") -> Chroma:
    """Initialize or load the Chroma vector store (cached as a singleton).

    The first call creates the ``Chroma`` instance; subsequent calls return
    the same object.  Call :func:`_invalidate_store` to force recreation
    (e.g. after ``reindex_all`` nukes the persistence directory).

    When *obs_store* is provided, all embedding operations (index, search)
    are logged to the SQLite observability store.
    """
    global _store_cache
    if _store_cache is not None:
        return _store_cache

    chroma_dir = _chroma_dir()
    embeddings = _get_embeddings(obs_store=obs_store, run_id=run_id)

    if not chroma_dir.exists():
        chroma_dir.mkdir(parents=True, exist_ok=True)

    _store_cache = Chroma(
        persist_directory=str(chroma_dir),
        embedding_function=embeddings,
        collection_name="wiki-pages",
    )
    return _store_cache


def _invalidate_store() -> None:
    """Drop the cached Chroma instance so the next call recreates it."""
    global _store_cache
    _store_cache = None


def index_page(path: str, content: str, *, obs_store: ObsStore | None = None, run_id: str = "") -> None:
    """Embed and index a wiki page in the Chroma store."""
    store = init_store(obs_store=obs_store, run_id=run_id)
    page_path = Path(path)

    # Remove existing entry for this page (by metadata filter)
    try:
        existing = store.get(where={"source": path})
        if existing["ids"]:
            store.delete(ids=existing["ids"])
    except Exception:
        pass  # Store might be empty

    doc = Document(
        page_content=content,
        metadata={
            "source": path,
            "title": page_path.stem,
        },
    )
    store.add_documents([doc])


def update_page(path: str, content: str, *, obs_store: ObsStore | None = None, run_id: str = "") -> None:
    """Update an existing page's embedding. Alias for index_page."""
    index_page(path, content, obs_store=obs_store, run_id=run_id)


def delete_page(path: str, *, obs_store: ObsStore | None = None, run_id: str = "") -> None:
    """Remove a page's embedding from the Chroma store."""
    store = init_store(obs_store=obs_store, run_id=run_id)
    try:
        existing = store.get(where={"source": path})
        if existing["ids"]:
            store.delete(ids=existing["ids"])
    except Exception:
        pass


def retrieve(query: str, k: int = 5, *, obs_store: ObsStore | None = None, run_id: str = "") -> list[Document]:
    """Retrieve the k most relevant wiki pages for a query."""
    store = init_store(obs_store=obs_store, run_id=run_id)
    return store.similarity_search(query, k=k)


def reindex_all(*, obs_store: ObsStore | None = None, run_id: str = "") -> int:
    """Rebuild the Chroma store from all wiki markdown files.

    When *obs_store* is provided, the bulk embedding operation is logged
    to the SQLite observability store.

    Returns the number of pages indexed.
    """
    chroma_dir = _chroma_dir()

    # Nuke existing store
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)

    _invalidate_store()
    store = init_store(obs_store=obs_store, run_id=run_id)
    wiki_dir = get_wiki_root() / "wiki"

    docs: list[Document] = []
    for md_file in sorted(wiki_dir.glob("*.md")):
        # Skip index.md and log.md — they're navigation, not content
        if md_file.name in ("index.md", "log.md"):
            continue

        content = md_file.read_text(encoding="utf-8")
        rel_path = f"wiki/{md_file.name}"
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source": rel_path,
                    "title": md_file.stem,
                },
            )
        )

    if docs:
        store.add_documents(docs)

    return len(docs)
