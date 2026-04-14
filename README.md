# Personal LLM Wiki (LangChain)

A personal knowledge base maintained by an AI agent. Drop raw sources into `raw/`, the agent extracts knowledge into structured wiki pages, and you can query and chat with your wiki.

## Quick Start

```bash
# Set up API keys (chat + embeddings required, Telegram optional)
export POE_API_KEY=poe-xxxxx-your-key           # Chat — uses your subscription credits
export OPENROUTER_API_KEY=sk-or-v1-your-key     # Embeddings — cheap pay-as-you-go
export TELEGRAM_BOT_TOKEN=123456:telegram-token # Optional — enables `wiki telegram poll`

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

# Telegram long polling
uv run wiki telegram poll

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
| `wiki telegram poll` | Long-poll Telegram private chats into the wiki agent |
| `wiki reindex` | Rebuild Chroma vector store |

## Architecture

- **Agent**: LangChain `create_agent()` with 13 tools and moderate system prompt
- **Chat model**: Default `gpt-4.1-mini` via Poe (set `WIKI_MODEL` / `WIKI_CHAT_BASE_URL` to override)
- **Embeddings**: `openai/text-embedding-3-small` via OpenRouter (set `WIKI_EMBED_MODEL` / `WIKI_EMBED_BASE_URL` to override)
- **RAG**: Chroma vector store for semantic page discovery
- **Chunking**: LangGraph long-source review flow (split → embed → summarize → review groups → synthesize drafts)
- **Validation**: Middleware linter for index.md and log.md format
- **HITL**: Configurable approval gates on ingest (`--approval=plan,page,commit,none`)
- **Telegram**: Optional long-poll transport with durable SQLite session state and LangGraph checkpoints

## Project Structure

```
raw/           # Immutable source documents (human-owned)
wiki/          # Agent-generated knowledge pages
  index.md     # Page index with categories
  log.md       # Append-only operation log
  .chroma/     # Derived vector store (gitignored)
scratch/       # Transient chunk artifacts
```
