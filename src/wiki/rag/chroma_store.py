"""Chroma vector store for semantic wiki page discovery."""

from __future__ import annotations

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from wiki.config import get_base_url, get_embedding_model, require_api_key


def _get_embeddings() -> OpenAIEmbeddings:
    """Create embeddings instance using the configured provider."""
    return OpenAIEmbeddings(
        model=get_embedding_model(),
        base_url=get_base_url(),
        api_key=require_api_key(),
    )


def _chroma_dir() -> Path:
    """Path to the Chroma persistence directory."""
    return Path.cwd() / "wiki" / ".chroma"


def init_store() -> Chroma:
    """Initialize or load the Chroma vector store."""
    chroma_dir = _chroma_dir()
    embeddings = _get_embeddings()

    if chroma_dir.exists():
        return Chroma(
            persist_directory=str(chroma_dir),
            embedding_function=embeddings,
            collection_name="wiki-pages",
        )

    chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        persist_directory=str(chroma_dir),
        embedding_function=embeddings,
        collection_name="wiki-pages",
    )


def index_page(path: str, content: str) -> None:
    """Embed and index a wiki page in the Chroma store."""
    store = init_store()
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


def update_page(path: str, content: str) -> None:
    """Update an existing page's embedding. Alias for index_page."""
    index_page(path, content)


def delete_page(path: str) -> None:
    """Remove a page's embedding from the Chroma store."""
    store = init_store()
    try:
        existing = store.get(where={"source": path})
        if existing["ids"]:
            store.delete(ids=existing["ids"])
    except Exception:
        pass


def retrieve(query: str, k: int = 5) -> list[Document]:
    """Retrieve the k most relevant wiki pages for a query."""
    store = init_store()
    return store.similarity_search(query, k=k)


def reindex_all() -> int:
    """Rebuild the Chroma store from all wiki markdown files.

    Returns the number of pages indexed.
    """
    chroma_dir = _chroma_dir()

    # Nuke existing store
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)

    store = init_store()
    wiki_dir = Path.cwd() / "wiki"

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
