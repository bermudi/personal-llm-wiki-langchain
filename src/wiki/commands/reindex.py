"""wiki reindex — rebuild Chroma vector store."""

from __future__ import annotations

from wiki.config import validate_wiki_dir
from wiki.rag.chroma_store import reindex_all


def run_reindex() -> None:
    cwd = validate_wiki_dir()
    count = reindex_all()
    print(f"Reindexed {count} wiki pages into Chroma store at wiki/.chroma/")
