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

The agent SHALL default to `openai/gpt-4.1-mini` as the model, connecting via OpenRouter API at `base_url=https://openrouter.ai/api/v1` using the `OPENROUTER_API_KEY` environment variable (falls back to `POE_API_KEY`). The model SHALL be overridable via the `WIKI_MODEL` environment variable. The base URL SHALL be overridable via `WIKI_BASE_URL`. The tool SHALL exit with a clear error if no API key is set.

#### Scenario: Default model
- **WHEN** no `WIKI_MODEL` env var is set
- **THEN** the agent uses `openai/gpt-4.1-mini` via OpenRouter

#### Scenario: Custom model
- **WHEN** `WIKI_MODEL=anthropic/claude-sonnet-4` is set
- **THEN** the agent uses that model instead

#### Scenario: Missing API key
- **WHEN** neither `OPENROUTER_API_KEY` nor `POE_API_KEY` is set
- **THEN** the tool prints "OPENROUTER_API_KEY (or POE_API_KEY) environment variable is required" and exits with code 1
