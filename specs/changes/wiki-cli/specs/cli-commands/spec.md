# CLI Commands

## ADDED Requirements

### Requirement: Init Command

The tool SHALL provide a `wiki init` command that creates the wiki workspace in the current working directory. It SHALL create `raw/`, `wiki/`, and `scratch/` directories, `wiki/index.md` with category sections, `wiki/log.md` with a header, and `.gitignore` ignoring `.obsidian/` and `wiki/.chroma/`. It SHALL make an initial git commit with message `bootstrap: initial workspace`.

#### Scenario: Fresh directory
- **WHEN** the user runs `uv run wiki init` in an empty directory
- **THEN** `raw/`, `wiki/`, `scratch/` directories exist, `wiki/index.md` and `wiki/log.md` contain scaffold content, `.gitignore` is created, and a single git commit exists

#### Scenario: Already initialized
- **WHEN** the user runs `uv run wiki init` in a directory that already contains `raw/`, `wiki/`, `scratch/`
- **THEN** the tool prints an error and exits without modifying anything

### Requirement: Ingest Command

The tool SHALL provide a `wiki ingest <path>` command that runs the wiki agent to process a raw source file. The agent reads the source, creates/updates wiki pages, updates the index and log, and commits atomically. The command SHALL accept an `--approval` flag with values `plan` (approve plan then autonomous), `page` (approve each page write), `commit` (approve final commit), `none` (fully autonomous), or a comma-separated combination (default: `plan,commit`).

#### Scenario: Short source ingest
- **WHEN** the user runs `uv run wiki ingest raw/2026-04-13-article-slug.md`
- **THEN** the agent reads the source, presents its plan for approval (by default), creates/updates wiki pages, updates index and log, and commits with message `ingest: <source-slug>`

#### Scenario: Long source with chunking
- **WHEN** the user ingests a source exceeding ~10k words
- **THEN** the agent detects the long source and uses chunking pipeline tools (split → extract → group → synthesize) to process it, guided by the system prompt

#### Scenario: No approval
- **WHEN** the user runs `uv run wiki ingest --approval=none raw/source.md`
- **THEN** the agent runs autonomously without pausing for approval at any gate

### Requirement: Query Command

The tool SHALL provide a `wiki query "<question>"` command that runs a one-shot query against the wiki. The agent discovers relevant pages via the Chroma vector store, reads them, synthesizes an answer with citations, and prints it to stdout. The agent autonomously decides whether to file the answer as a wiki page.

#### Scenario: Factual question
- **WHEN** the user runs `uv run wiki query "What does X say about Y?"`
- **THEN** the agent retrieves relevant pages from Chroma, synthesizes an answer with citations, prints it, and optionally creates a wiki page if the answer has lasting value

#### Scenario: Quick lookup
- **WHEN** the user asks a simple factual question
- **THEN** the agent answers in chat without creating any wiki files

### Requirement: Chat Command

The tool SHALL provide a `wiki chat` command that opens an interactive REPL with the wiki agent. The agent maintains conversation state across turns using a LangChain checkpointer. Each turn has the same capabilities as the query command.

#### Scenario: Multi-turn conversation
- **WHEN** the user runs `uv run wiki chat` and asks a question, then a follow-up
- **THEN** the agent remembers the previous turn's context and can build on it

#### Scenario: Exit
- **WHEN** the user presses Ctrl-D or types `exit`
- **THEN** the session ends gracefully

### Requirement: Reindex Command

The tool SHALL provide a `wiki reindex` command that rebuilds the Chroma vector store from all current wiki pages. This is a maintenance command for when pages are added or changed outside the agent.

#### Scenario: Rebuild after manual edits
- **WHEN** the user runs `uv run wiki reindex`
- **THEN** all wiki markdown files are re-embedded into a fresh Chroma store at `wiki/.chroma/`, and the previous store is replaced

### Requirement: Wiki Detection

All commands except `init` SHALL validate that `raw/`, `wiki/`, and `scratch/` directories exist in the current working directory before executing. If any are missing, the tool SHALL print a clear error message suggesting `wiki init` and exit.

#### Scenario: Missing directories
- **WHEN** the user runs `uv run wiki query "something"` in a directory without `raw/`, `wiki/`, `scratch/`
- **THEN** the tool prints "Not a wiki directory. Run `wiki init` first." and exits with code 1

#### Scenario: Valid wiki directory
- **WHEN** the user runs any command in a directory with the expected structure
- **THEN** the command proceeds normally
