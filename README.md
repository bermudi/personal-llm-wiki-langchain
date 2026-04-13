# Personal LLM Wiki (LangChain)

A personal knowledge base maintained by an AI agent. Drop raw sources into `raw/`, the agent extracts knowledge into structured wiki pages, and you can query and chat with your wiki.

## Quick Start

```bash
# Set up your API key
export POE_API_KEY=poe-xxxxx-your-key

# Initialize a wiki workspace
mkdir my-wiki && cd my-wiki
uv run --project /path/to/personal-llm-wiki-langchain wiki init

# Ingest a source
cp ~/notes/podcast-transcript.md raw/2026-04-13-podcast.md
uv run wiki ingest raw/2026-04-13-podcast.md

# Query the wiki
uv run wiki query "What did they say about institutional trust?"

# Interactive chat
uv run wiki chat

# Rebuild the search index
uv run wiki reindex
```

## Commands

| Command | Description |
|---------|-------------|
| `wiki init` | Create wiki workspace (raw/, wiki/, scratch/) |
| `wiki ingest <path>` | Process a source file into wiki pages |
| `wiki query "<question>"` | One-shot question with citations |
| `wiki chat` | Interactive multi-turn conversation |
| `wiki reindex` | Rebuild Chroma vector store |

## Architecture

- **Agent**: LangChain `create_agent()` with 13 tools and moderate system prompt
- **Model**: Default `gpt-5.4` via Poe API (set `WIKI_MODEL` to override)
- **RAG**: Chroma vector store for semantic page discovery
- **Chunking**: Pipeline tools for long sources (split → extract → group → synthesize)
- **Validation**: Middleware linter for index.md and log.md format
- **HITL**: Configurable approval gates on ingest (`--approval=plan,page,commit,none`)

## Project Structure

```
raw/           # Immutable source documents (human-owned)
wiki/          # Agent-generated knowledge pages
  index.md     # Page index with categories
  log.md       # Append-only operation log
  .chroma/     # Derived vector store (gitignored)
scratch/       # Transient chunk artifacts
```
