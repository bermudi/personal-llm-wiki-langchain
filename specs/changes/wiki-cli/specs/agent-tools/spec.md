# Agent Tools

## ADDED Requirements

### Requirement: Filesystem Tools

The agent SHALL have access to filesystem tools for reading and writing wiki content: `read_file(path)` for reading any file, `write_file(path, content)` for creating or overwriting files, `edit_file(path, old_text, new_text)` for targeted edits, `list_files(directory)` for listing directory contents, and `search_files(pattern)` for grep-style search across wiki files.

#### Scenario: Reading a raw source
- **WHEN** the agent calls `read_file("raw/2026-04-13-podcast.md")`
- **THEN** the full file contents are returned as a string

#### Scenario: Creating a wiki page
- **WHEN** the agent calls `write_file("wiki/some-topic.md", content)`
- **THEN** the file is created with the given content

#### Scenario: Searching across wiki
- **WHEN** the agent calls `search_files("institutional trust")`
- **THEN** all wiki files containing that phrase are returned with context

### Requirement: Git Tools

The agent SHALL have access to git tools: `git_status()` for checking the working tree state, `git_commit(message)` for atomic commits of all staged changes, and `git_log(n)` for viewing recent commit history. The commit message SHALL follow the pattern `<operation>: <description>`.

#### Scenario: Checking for human edits
- **WHEN** the agent calls `git_status()` and a wiki file has uncommitted changes
- **THEN** the tool returns the list of dirty files so the agent knows to preserve those edits

#### Scenario: Atomic commit
- **WHEN** the agent calls `git_commit("ingest: podcast-guest-topic")`
- **THEN** all changed files are committed in a single commit with that message

#### Scenario: Recent history
- **WHEN** the agent calls `git_log(5)`
- **THEN** the last 5 commits are returned with messages and dates

### Requirement: Chunking Pipeline Tools

The agent SHALL have access to chunking pipeline tools: `split_source(path, chunk_size)` for mechanically splitting a long source into size-bounded chunks at natural boundaries, `extract_chunk(chunk_path)` for LLM-powered extraction of a structured note from a chunk, `group_chunks(chunk_paths)` for LLM-powered semantic grouping of related chunks, and `synthesize_group(group)` for LLM-powered synthesis over a chunk group.

#### Scenario: Splitting a long transcript
- **WHEN** the agent calls `split_source("raw/2026-04-13-podcast.md", 5000)`
- **THEN** the source is split into roughly equal chunks at paragraph or speaker-turn boundaries, saved to `scratch/<source-slug>/chunk-NNN.md`, and chunk paths are returned

#### Scenario: Extracting from a chunk
- **WHEN** the agent calls `extract_chunk("scratch/2026-04-13-podcast/chunk-001.md")`
- **THEN** a structured extraction note is produced containing topics, entities/people, key claims, notable quotes, and unresolved questions

#### Scenario: Grouping related chunks
- **WHEN** the agent calls `group_chunks(["chunk-001.md", "chunk-002.md", "chunk-005.md"])`
- **THEN** chunks are grouped by semantic similarity, returning topic-linked clusters that may span temporally distant segments

#### Scenario: Synthesizing a group
- **WHEN** the agent calls `synthesize_group(group)` on a topic-linked cluster
- **THEN** relevant chunk notes and source segments are synthesized into unified wiki page content
