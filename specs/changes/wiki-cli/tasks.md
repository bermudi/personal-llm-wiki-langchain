## Phase 1: Package Skeleton and CLI Entry Point

- [x] Create `pyproject.toml` with dependencies (`langchain`, `langchain-openai`, `langchain-community`, `chromadb`, `typer`, `rich`), console script `wiki = wiki.cli:app`, Python 3.14 target — Project Structure (Python Package Structure)
- [x] Create `src/wiki/__init__.py` (empty)
- [x] Create `src/wiki/config.py` with `POE_API_KEY` loader (required, exits with error if missing), `WIKI_MODEL` loader (default `gpt-5.4`), wiki directory validator (`raw/`, `wiki/`, `scratch/` must exist), and model instance builder using `ChatOpenAI(base_url="https://api.poe.com/v1")` — Project Structure (Model Configuration)
- [x] Create `src/wiki/cli.py` with typer app skeleton and five stub subcommands: `init`, `ingest`, `query`, `chat`, `reindex`. All commands except `init` call wiki directory validator — CLI Commands (Init, Ingest, Query, Chat, Reindex, Wiki Detection)
- [x] Verify `uv run wiki --help` prints the subcommand list without errors
- [x] Verify `uv run wiki query "test"` in a non-wiki directory prints "Not a wiki directory" and exits with code 1

## Phase 2: Init Command and Project Structure

- [x] Implement `wiki init` command: create `raw/`, `wiki/`, `scratch/` directories, write `wiki/index.md` with category sections (entities, concepts, sources, syntheses, meta), write `wiki/log.md` with header scaffold, write `.gitignore` with `.obsidian/` and `wiki/.chroma/`, run `git init` if needed, commit as `bootstrap: initial workspace` — CLI Commands (Init Command), Project Structure (Directory Layout)
- [x] Verify `uv run wiki init` in a temp directory creates all expected files and a single git commit
- [x] Verify running `uv run wiki init` again in the same directory prints an error and does not modify anything

## Phase 3: Filesystem and Git Tools

- [x] Create `src/wiki/tools/__init__.py`
- [x] Create `src/wiki/tools/filesystem.py` with five `@tool` functions: `read_file`, `write_file`, `edit_file`, `list_files`, `search_files`. All paths resolved relative to cwd. `search_files` uses `subprocess` to call `rg` or falls back to Python `re` — Agent Tools (Filesystem Tools)
- [x] Create `src/wiki/tools/git.py` with three `@tool` functions: `git_status` (returns dirty files), `git_commit` (stages all, commits with given message), `git_log` (returns last N commits) — Agent Tools (Git Tools), Git Protocol (all requirements)
- [x] Write a test that calls each tool directly and verifies expected behavior (read a file, write a file, check git status, commit, check git log)

## Phase 4: Agent Construction

- [x] Create `src/wiki/agent.py` with `create_wiki_agent()` function that constructs a LangChain agent using `create_agent()` with: model from config, all filesystem and git tools, moderate system prompt (three-layer architecture, git convention, chunking guidance, citation behavior, filing guidance, orient-yourself nudge), optional checkpointer parameter — Agent Tools (all), Project Structure (Model Configuration)
- [x] Verify the agent can be constructed and responds to a simple message without tools
- [x] Verify the agent can invoke `read_file` and `list_files` tools against a test wiki directory

## Phase 5: Ingest Command with HITL

- [x] Implement `wiki ingest <path>` command: validate wiki dir, construct agent with checkpointer (for HITL interrupt/resume), invoke agent with ingest prompt including the source path and `--approval` flag configuration — CLI Commands (Ingest Command)
- [x] Implement HITL approval gates based on `--approval` flag: `plan` (interrupt after agent presents plan, resume on approval), `page` (interrupt before each page write), `commit` (interrupt before final commit), `none` (no interrupts), `plan,commit` (default) — CLI Commands (Ingest Command)
- [x] Verify `uv run wiki ingest --approval=none raw/test-source.md` against a test wiki creates wiki pages, updates index and log, and commits atomically (requires POE_API_KEY for live test)
- [x] Verify `uv run wiki ingest raw/test-source.md` (default approval) pauses for plan approval and commit approval (requires POE_API_KEY for live test)
- [x] Verify the commit message follows `<operation>: <description>` format

## Phase 6: Middleware (Index/Log Linter)

- [x] Create `src/wiki/middleware/__init__.py`
- [x] Create `src/wiki/middleware/linter.py` with custom middleware that intercepts `write_file` and `edit_file` calls targeting `wiki/index.md` or `wiki/log.md`, validates format, and rejects malformed writes with descriptive errors — Middleware (Index Format Linter, Log Format Linter)
- [x] Index validation: each entry has a link and one-line summary under a category heading, no duplicate entries
- [x] Log validation: entries follow `## [YYYY-MM-DD] <operation> | <description>` with at least one bullet, append-only
- [x] Wire the linter middleware into the agent construction in `agent.py`
- [x] Verify that a malformed index write is rejected and the agent receives the error message
- [x] Verify that a malformed log write is rejected and the agent receives the error message
- [x] Verify that well-formed index and log writes pass through

## Phase 7: Chunking Pipeline Tools

- [x] Create `src/wiki/tools/chunking.py` with four `@tool` functions — Agent Tools (Chunking Pipeline Tools), Chunking Pipeline (all requirements)
- [x] `split_source(path, chunk_size=5000)`: read source, split at natural boundaries (paragraph breaks, speaker turns), save chunks to `scratch/<source-slug>/chunk-NNN.md`, return chunk paths
- [x] `extract_chunk(chunk_path)`: read chunk, call LLM for structured extraction (topics, entities, claims, quotes, questions), write structured note back to chunk path, return extraction summary
- [x] `group_chunks(chunk_paths)`: read all chunk notes, call LLM to identify semantic groups, return grouped clusters
- [x] `synthesize_group(group)`: read chunk notes for the group, call LLM to synthesize unified content, return synthesized wiki page content
- [x] Add chunking tools to the agent's tool inventory in `agent.py`
- [x] Test `split_source` with a 15k-word synthetic transcript: verify 3+ chunks are created in `scratch/`
- [x] Test `extract_chunk` on one chunk: verify the structured note contains all five fields (topics, entities, claims, quotes, questions) (requires POE_API_KEY for live test)
- [x] Test `group_chunks` on extracted chunks: verify related chunks are grouped together (requires POE_API_KEY for live test)

## Phase 8: RAG with Chroma

- [x] Create `src/wiki/rag/__init__.py`
- [x] Create `src/wiki/rag/chroma_store.py` with Chroma vector store management: `init_store()` (create/load), `index_page(path, content)`, `update_page(path, content)`, `delete_page(path)`, `retrieve(query, k=5)` — RAG Discovery (all requirements)
- [x] Use LangChain's Chroma integration with embeddings via `langchain-openai` pointed at Poe's API
- [x] Implement `wiki reindex` command: delete `wiki/.chroma/`, enumerate all `wiki/*.md` files, embed and store each — CLI Commands (Reindex Command)
- [x] Add a `search_wiki(query)` tool that wraps `chroma_store.retrieve()` and exposes it to the agent
- [x] Verify `uv run wiki reindex` builds a Chroma store from test wiki pages (requires POE_API_KEY for live test)
- [x] Verify `search_wiki` retrieves relevant pages for a test query (requires POE_API_KEY for live test)

## Phase 9: Query and Chat Commands

- [x] Implement `wiki query "<question>"` command: validate wiki dir, construct agent without checkpointer, invoke agent with query prompt, print result to stdout — CLI Commands (Query Command)
- [x] Verify `uv run wiki query "What is in the wiki?"` returns a synthesized answer with citations (requires POE_API_KEY for live test)
- [x] Implement `wiki chat` command: validate wiki dir, construct agent with `MemorySaver` checkpointer and generated `thread_id`, run interactive REPL loop, exit on Ctrl-D or "exit" — CLI Commands (Chat Command)
- [x] Verify multi-turn conversation: ask a question, then a follow-up, confirm the agent has context from the first turn (requires POE_API_KEY for live test)

## Phase 10: End-to-End Validation

- [x] Full ingest smoke test: `wiki init` → add test source to `raw/` → `wiki ingest` → verify wiki pages created, index updated, log appended, Chroma updated, single git commit (requires POE_API_KEY)
- [x] Long-source smoke test: ingest a 15k+ word synthetic transcript → verify chunking pipeline fires (chunks in `scratch/`), multiple wiki pages created from grouped chunks, cross-chunk themes captured (requires POE_API_KEY)
- [x] Query smoke test: `wiki query` against the ingested wiki → verify answer includes citations to wiki pages (requires POE_API_KEY)
- [x] Chat smoke test: `wiki chat` → ask two related questions → verify multi-turn context (requires POE_API_KEY)
- [x] Verify `git log --oneline` shows operation-prefixed commits in readable order
- [x] Verify reindex: `wiki reindex` rebuilds Chroma, then query still works (requires POE_API_KEY)
