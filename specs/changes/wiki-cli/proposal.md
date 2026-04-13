## Motivation

The original personal-llm-wiki is a pure prompt-engineering project — an LLM reads a schema document (`AGENTS.md`) and follows natural language procedures to maintain a wiki. It works, but the procedures are only as reliable as the LLM's discipline. The LLM can forget to update the index, skip a git commit, or go off-script during chunking.

This change rebuilds the wiki as a Python CLI tool powered by LangChain. The key difference: the agent's procedures are enforced through tool calls and middleware rather than prompt prose. The LLM can't forget to validate the index format because middleware rejects malformed writes. It can't skip git commit because it's a tool in the loop. The wiki stays maintained because the *code* ensures it, not the LLM's reading comprehension.

## Scope

- **CLI entry point** (`uv run wiki`): `init`, `ingest`, `query`, `chat`, and `reindex` subcommands using `typer`
- **Wiki detection**: tool validates `raw/`, `wiki/`, `scratch/` exist in `cwd`; errors clearly if not
- **Agent construction**: `create_agent()` from LangChain with a moderate system prompt (three-layer architecture, git convention, chunking guidance, citation and filing guidance)
- **Chat model**: default `gpt-4.1-mini` via Poe API (`base_url=https://api.poe.com/v1`, auth via `POE_API_KEY`), overridable with `WIKI_MODEL`. Uses Poe subscription credits for the expensive chat calls.
- **Embeddings**: default `openai/text-embedding-3-small` via OpenRouter (`base_url=https://openrouter.ai/api/v1`, auth via `OPENROUTER_API_KEY`), overridable with `WIKI_EMBED_MODEL`. Embeddings are cheap pay-as-you-go (~$0.02/1M tokens). Two separate providers keeps costs on the right billing surface.
- **Tool inventory**: filesystem tools (`read_file`, `write_file`, `edit_file`, `list_files`, `search_files`), git tools (`git_status`, `git_commit`, `git_log`), chunking pipeline tools (`split_source`, `extract_chunk`, `group_chunks`, `synthesize_group`)
- **Middleware**: index/log format linter that validates structure immediately after any `write_file` touching `wiki/index.md` or `wiki/log.md`
- **`init` command**: creates `raw/`, `wiki/`, `scratch/`, `wiki/index.md`, `wiki/log.md`, `.gitignore`; makes initial git commit; no interactive grill-me
- **`ingest` command**: agent reads source, creates/updates wiki pages, updates index/log, commits atomically. Human-in-the-loop approval gates configurable via `--approval` flag (default: `plan,commit`, options: `plan`, `page`, `commit`, `none`, or comma-separated combinations)
- **`query` command**: one-shot question against the wiki. Agent uses Chroma vector store for semantic page discovery, synthesizes answer with citations, autonomously decides whether to file as a page
- **`chat` command**: interactive REPL with checkpointer for multi-turn conversation. Same agent capabilities as query but persistent across turns
- **Chunking pipeline**: for long sources (~10k+ words), agent uses pipeline tools with soft guardrails (system prompt guides split → extract → group → synthesize, agent can deviate with judgment). Chunk notes persisted in `scratch/<source-slug>/chunk-NNN.md` with structured fields (topics, entities, claims, quotes, questions)
- **RAG with Chroma**: embedding-based page discovery using Chroma vector store. Wiki pages are embedded and indexed. `reindex` command rebuilds the store from current wiki pages. Store lives at `wiki/.chroma/` (gitignored, derived)
- **Git protocol**: agent always commits atomically with `<operation>: <description>` messages. Dirty working tree = human edits = authoritative. Agent checks `git_status` before modifying wiki files

## Non-Goals

- Web UI, Obsidian plugin, or server mode — CLI only
- Multi-user or collaboration features
- Image, audio, or video preprocessing — text only for now
- Error correction infrastructure beyond git revert
- Configurable system prompt or user-editable schema file — the code is the schema
- Scaling infrastructure beyond Chroma — cross that bridge when it hurts
- The grill-me bootstrap flow — replaced by silent `init`
- Source format detection or preprocessing beyond plain text/markdown
