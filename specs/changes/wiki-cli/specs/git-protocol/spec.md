# Git Protocol

## ADDED Requirements

### Requirement: Atomic Commits

The agent SHALL commit its changes atomically — each logical operation results in exactly one git commit containing all affected files. The agent SHALL NOT leave uncommitted changes in the working tree after completing an operation.

#### Scenario: Ingest completes
- **WHEN** the agent finishes ingesting a source and updating all relevant wiki pages, index, and log
- **THEN** all changes are committed in a single atomic commit with message `ingest: <source-slug>`

#### Scenario: Query produces a filed page
- **WHEN** the agent answers a query and files the answer as a wiki page
- **THEN** the new page, updated index, updated log, and updated Chroma store are committed together

### Requirement: Human Edit Authority

The agent SHALL check `git_status` before modifying any wiki file. If a file has uncommitted changes (dirty working tree), the agent SHALL treat those changes as human-authored and authoritative. The agent MUST integrate its new work around the human's edits rather than overwriting them.

#### Scenario: Human edited a page between sessions
- **WHEN** the agent reads a wiki page and finds it has uncommitted changes via `git_status`
- **THEN** the agent reads the current file content, preserves human edits, integrates new information around them, and commits the merged result

#### Scenario: No human edits present
- **WHEN** `git_status` shows no uncommitted changes for a wiki file
- **THEN** the agent freely updates the page as needed

### Requirement: Commit Message Convention

Commit messages SHALL follow the pattern `<operation>: <description>` where operation is one of `ingest`, `query`, `lint`, `schema`, or `bootstrap`. This makes the git log parseable.

#### Scenario: Browsing git log
- **WHEN** the user runs `git log --oneline`
- **THEN** commits are identifiable by operation type (e.g., "ingest: podcast guest topic", "query: comparison of X and Y")
