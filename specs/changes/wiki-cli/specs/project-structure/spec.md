# Project Structure

## ADDED Requirements

### Requirement: Directory Layout

The project SHALL consist of three top-level directories with distinct ownership semantics: `raw/` for immutable source documents owned by the human, `wiki/` for agent-generated knowledge pages, and `scratch/` for transient working artifacts produced during chunking. The `wiki/.chroma/` directory stores the derived Chroma vector store and SHALL be gitignored.

#### Scenario: Fresh `wiki init`
- **WHEN** the user runs `uv run wiki init`
- **THEN** the project contains `raw/`, `wiki/`, and `scratch/` directories, plus `wiki/index.md`, `wiki/log.md`, and `.gitignore`

#### Scenario: Scratch artifacts after ingest
- **WHEN** the agent processes a long transcript using the chunking pipeline
- **THEN** per-chunk extraction notes are saved under `scratch/<source-slug>/chunk-NNN.md`

### Requirement: Raw Source Naming

All raw source files SHALL use date-prefixed filenames in `YYYY-MM-DD-descriptive-slug.md` format. The raw directory SHALL be flat with no subdirectories. The agent SHALL read from `raw/` but never modify or delete files within it.

#### Scenario: Adding a new podcast transcript
- **WHEN** the user saves a transcript to the raw directory
- **THEN** the file is named e.g. `raw/2026-04-13-podcast-guest-topic.md` and is treated as immutable

### Requirement: Python Package Structure

The tool SHALL be structured as a Python package with `pyproject.toml` for dependency management. The CLI entry point SHALL be `wiki` registered as a console script. The package SHALL use `uv` for dependency management and execution.

#### Scenario: Running the tool
- **WHEN** the user runs `uv run wiki init`
- **THEN** the CLI entry point resolves and the command executes

### Requirement: Model Configuration

The agent SHALL use two separate providers for chat and embeddings.

**Chat provider** (expensive, uses subscription credits):
- Default model: `gpt-4.1-mini` via Poe API at `https://api.poe.com/v1`
- Auth: `POE_API_KEY` environment variable (required)
- Override: `WIKI_MODEL` and `WIKI_CHAT_BASE_URL` env vars

**Embedding provider** (cheap, pay-as-you-go):
- Default model: `openai/text-embedding-3-small` via OpenRouter at `https://openrouter.ai/api/v1`
- Auth: `OPENROUTER_API_KEY` environment variable (required)
- Override: `WIKI_EMBED_MODEL` and `WIKI_EMBED_BASE_URL` env vars

The tool SHALL exit with a clear error if either key is missing when its provider is needed.

#### Scenario: Default configuration
- **WHEN** no env vars are set except `POE_API_KEY` and `OPENROUTER_API_KEY`
- **THEN** chat uses `gpt-4.1-mini` via Poe, embeddings use `openai/text-embedding-3-small` via OpenRouter

#### Scenario: Custom chat model
- **WHEN** `WIKI_MODEL=anthropic/claude-sonnet-4` is set
- **THEN** the agent uses that model via Poe

#### Scenario: Missing Poe key
- **WHEN** `POE_API_KEY` is not set and chat is needed
- **THEN** prints error and exits with code 1

#### Scenario: Missing OpenRouter key
- **WHEN** `OPENROUTER_API_KEY` is not set and embeddings are needed
- **THEN** prints error and exits with code 1
