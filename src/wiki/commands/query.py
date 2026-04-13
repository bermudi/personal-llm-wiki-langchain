"""wiki query — one-shot question."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from wiki.agent import create_wiki_agent
from wiki.config import validate_wiki_dir
from wiki.middleware.linter import create_linter_middleware

console = Console()


def run_query(question: str) -> None:
    cwd = validate_wiki_dir()

    agent = create_wiki_agent(
        middleware=[create_linter_middleware()],
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

    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 15},
    )

    answer = result["messages"][-1].content
    console.print(Markdown(answer))
