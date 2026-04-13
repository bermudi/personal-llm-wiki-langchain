## Architecture

```
personal-llm-wiki-langchain/
├── pyproject.toml                  # uv package config, console script entry point
├── src/
│   └── wiki/
│       ├── __init__.py
│       ├── cli.py                  # typer app: init, ingest, query, chat, reindex
│       ├── agent.py                # create_agent() construction, system prompt
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── filesystem.py       # read_file, write_file, edit_file, list_files, search_files
│       │   ├── git.py              # git_status, git_commit, git_log
│       │   └── chunking.py         # split_source, extract_chunk, group_chunks, synthesize_group
│       ├── middleware/
│       │   ├── __init__.py
│       │   └── linter.py           # index + log format validation after writes
│       ├── rag/
│       │   ├── __init__.py
│       │   └── chroma_store.py     # Chroma vector store management, embedding, retrieval
│       └── config.py               # model config, env var loading, path validation
├── raw/                            # Immutable sources (human-owned)
├── wiki/                           # Agent-generated knowledge base
│   ├── index.md
│   ├── log.md
│   └── .chroma/                    # Derived vector store (gitignored)
└── scratch/                        # Transient chunk artifacts
```

**Data flow:**

1. User runs CLI command → `cli.py` validates wiki directory → constructs agent via `agent.py`
2. Agent runs with tools + middleware → calls LLM via Poe API → uses tools to read/write/search
3. Middleware intercepts writes to `index.md` and `log.md` → validates format → rejects malformed writes
4. RAG layer embeds new/updated wiki pages into Chroma → available for future queries
5. Git tools commit changes atomically at operation boundaries

**Two agent modes:**

- **Ingest/query**: `create_agent()` with full tool inventory, checkpointer only for ingest (to support HITL interrupts)
- **Chat**: `create_agent()` with `MemorySaver` checkpointer and `thread_id` for multi-turn persistence

## Decisions

### Split providers: Poe for chat, OpenRouter for embeddings
- **Chosen:** Route chat completions through Poe (subscription credits) and embeddings through OpenRouter (pay-as-you-go)
- **Why:** Chat is expensive — use the Poe subscription you're already paying for. Embeddings are ~$0.02/1M tokens — pocket change on OpenRouter. Poe doesn't offer embeddings at all. Both use the same `ChatOpenAI`/`OpenAIEmbeddings` from `langchain-openai`, just different `base_url` and `api_key`
- **Trade-off:** Two API keys to manage. Acceptable since they serve different purposes and you're already paying for both

### Chroma over FAISS for vector store
- **Chosen:** Chroma as the embedded vector store
- **Why:** Persistent storage out of the box, no file serialization code needed, future server mode if the wiki scales to need it. Heavier than FAISS but the DX is better
- **Trade-off:** Adds `chromadb` as a dependency. Acceptable for the feature set

### Typer for CLI
- **Chosen:** Typer for the CLI framework
- **Why:** Clean type-annotated API, automatic help text, built on click, Pythonic. Standard choice for modern Python CLIs
- **Constraint:** Adds `typer` dependency

### Soft guardrails for chunking pipeline
- **Chosen:** System prompt guides the chunking flow (split → extract → group → synthesize), but the agent can deviate with judgment. No enforced ordering in tool code
- **Why:** Consistent with the project's philosophy of trusting the agent. A simple source might not need grouping. A dense source might need multiple grouping passes. Hard guardrails would over-constrain
- **Trade-off:** The agent might skip steps. Acceptable because the HITL approval gates catch problems before commit

### Middleware as write validator, not pre-commit hook
- **Chosen:** Index/log linter runs immediately after `write_file`/`edit_file` touches those files, not at commit time
- **Why:** Instant feedback to the agent — it knows the write is malformed and can fix it right away. Pre-commit would let bad writes accumulate and require unwinding
- **Constraint:** Only validates format, not semantic correctness (e.g., doesn't check that referenced pages exist on disk)

### Tools as plain LangChain @tool functions
- **Chosen:** Each tool is a `@tool`-decorated Python function, not a LangGraph node or custom class
- **Why:** Simplest surface area. The agent loop is `create_agent()` which handles tool dispatch. No graph overhead for the main agent
- **Trade-off:** Chunking pipeline tools call the LLM internally (e.g., `extract_chunk` makes its own LLM call), which means nested LLM invocations. Acceptable — each tool call is focused and bounded

### System prompt lives in code, not in a user-editable file
- **Chosen:** The system prompt is a Python string in `agent.py`, not a markdown file the user edits
- **Why:** The code IS the schema. Keeping it in code means version control, no stale file issues, and no ambiguity about what the agent is instructed to do. If users want domain tuning, they can fork or we add config later
- **Trade-off:** Less user-configurable than the original AGENTS.md approach. That's the trade-off — code enforceability over user flexibility

## File Changes

### `pyproject.toml` — create
Package configuration with dependencies: `langchain`, `langchain-openai`, `langchain-community`, `chromadb`, `typer`, `rich`. Console script entry point `wiki = wiki.cli:app`. Python 3.14 target.

Relates to: Project Structure (Python Package Structure)

### `src/wiki/__init__.py` — create
Empty package init.

### `src/wiki/cli.py` — create
Typer app with five subcommands: `init`, `ingest`, `query`, `chat`, `reindex`. Each command validates the wiki directory (except `init`), loads config, constructs the agent, and runs it. `ingest` accepts `--approval` flag.

Relates to: CLI Commands (all requirements)

### `src/wiki/agent.py` — create
Agent construction: `create_agent()` with model from config, full tool inventory, moderate system prompt, optional checkpointer. System prompt content: three-layer architecture overview, git convention (atomic commits, dirty = human), chunking pipeline guidance, citation behavior, filing guidance, orient-yourself nudge.

Relates to: Project Structure (Model Configuration), Agent Tools (all requirements)

### `src/wiki/config.py` — create
Two separate provider configs:
- **Chat**: `POE_API_KEY` (required), `WIKI_MODEL` (default `gpt-4.1-mini`), `WIKI_CHAT_BASE_URL` (default `https://api.poe.com/v1`)
- **Embeddings**: `OPENROUTER_API_KEY` (required), `WIKI_EMBED_MODEL` (default `openai/text-embedding-3-small`), `WIKI_EMBED_BASE_URL` (default `https://openrouter.ai/api/v1`)
Wiki directory validation function. Model instance construction using `ChatOpenAI(base_url=..., api_key=...)`.

Relates to: Project Structure (Model Configuration)

### `src/wiki/tools/filesystem.py` — create
Five `@tool` functions: `read_file`, `write_file`, `edit_file`, `list_files`, `search_files`. All paths resolved relative to wiki root (cwd). `search_files` uses `rg` or Python `re` for grep-style search.

Relates to: Agent Tools (Filesystem Tools)

### `src/wiki/tools/git.py` — create
Three `@tool` functions: `git_status`, `git_commit`, `git_log`. `git_commit` stages all changes before committing with the operation-prefixed message.

Relates to: Agent Tools (Git Tools), Git Protocol (all requirements)

### `src/wiki/tools/chunking.py` — create
Four `@tool` functions: `split_source`, `extract_chunk`, `group_chunks`, `synthesize_group`. Each makes its own LLM call internally using the configured model. `split_source` is mechanical (no LLM). `extract_chunk` produces structured notes with topics/entities/claims/quotes/questions fields.

Relates to: Agent Tools (Chunking Pipeline Tools), Chunking Pipeline (all requirements)

### `src/wiki/middleware/linter.py` — create
Custom middleware that intercepts `write_file` and `edit_file` tool calls. If the target path is `wiki/index.md` or `wiki/log.md`, validates the format before allowing the write. Returns an error message to the agent on validation failure.

Relates to: Middleware (Index Format Linter, Log Format Linter)

### `src/wiki/rag/chroma_store.py` — create
Chroma vector store management: initialization, page embedding, page update, page deletion, semantic retrieval. Uses LangChain's Chroma integration with OpenAI-compatible embeddings via Poe. Exposes `index_page()`, `update_page()`, `delete_page()`, `retrieve(query, k)` functions. Used by the agent tools and the `reindex` command.

Relates to: RAG Discovery (all requirements)

### `.gitignore` — create (by `init` command)
Ignores `.obsidian/` and `wiki/.chroma/`.

Relates to: Project Structure (Directory Layout)
