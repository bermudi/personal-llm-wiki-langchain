"""wiki query — one-shot question with streaming and observability."""

from __future__ import annotations

import uuid

from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console

from wiki.agent import create_wiki_agent
from wiki.config import validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware
from wiki.observability import create_observability_middleware, init_run
from wiki.streaming import stream_agent_response

console = Console()


def run_query(question: str) -> None:
    cwd = validate_wiki_dir()

    thread_id = f"query-{uuid.uuid4().hex[:8]}"

    # Observability
    store, run_id = init_run("query", thread_id)
    obs_middleware = create_observability_middleware(store, run_id)

    agent = create_wiki_agent(
        checkpointer=MemorySaver(),
        middleware=[
            create_linter_middleware(),
            *obs_middleware,
        ],
    )

    prompt = f"""Answer this question using the wiki: {question}

Steps:
1. Read wiki/index.md to orient yourself
2. Use search_wiki to find relevant pages
3. Read the most relevant pages
4. Synthesize an answer with citations (link to the wiki pages you reference)
5. If the answer has lasting value, consider creating a wiki page for it and updating index/log
6. If it's a simple lookup, just answer without filing

Answer directly and cite your sources.
"""

    try:
        event_stream = agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 100,
            },
            stream_mode="messages",
        )
        stream_agent_response(event_stream)
        console.print()
    finally:
        store.close()
