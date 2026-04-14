"""wiki reindex — rebuild Chroma vector store."""

from __future__ import annotations

import uuid

from wiki.config import validate_wiki_dir
from wiki.observability import init_run
from wiki.rag.chroma_store import reindex_all


def run_reindex() -> None:
    cwd = validate_wiki_dir()

    thread_id = f"reindex-{uuid.uuid4().hex[:8]}"
    store, run_id = init_run("reindex", thread_id)
    try:
        count = reindex_all(obs_store=store, run_id=run_id)
        print(f"Reindexed {count} wiki pages into Chroma store at wiki/.chroma/")
    finally:
        store.close()
