# RAG Discovery

## ADDED Requirements

### Requirement: Chroma Vector Store

The tool SHALL maintain a Chroma vector store at `wiki/.chroma/` for semantic page discovery. Each wiki page SHALL be embedded and indexed with metadata including the page path and a content snippet. The store SHALL be gitignored as a derived artifact that can be rebuilt from source files.

#### Scenario: Indexing a new page
- **WHEN** the agent creates a new wiki page during ingest
- **THEN** the page is embedded and added to the Chroma store

#### Scenario: Updating an existing page
- **WHEN** the agent updates an existing wiki page
- **THEN** the old embedding is replaced with the updated content's embedding

#### Scenario: Deleting a page
- **WHEN** a wiki page is removed
- **THEN** its embedding is removed from the Chroma store

### Requirement: Semantic Page Retrieval

The agent SHALL use the Chroma vector store to discover relevant wiki pages when answering queries. Given a question, the agent retrieves the most semantically similar pages and reads them before synthesizing an answer.

#### Scenario: Targeted question
- **WHEN** the user asks "What does X say about Y?"
- **THEN** the agent queries Chroma with the question, retrieves the top-k most relevant pages, reads them in full, and synthesizes an answer

#### Scenario: Exploratory question
- **WHEN** the user asks a broad question like "What are the main themes?"
- **THEN** the agent queries Chroma with a higher k value to sample broadly across the wiki

### Requirement: Reindex Command

The `wiki reindex` command SHALL rebuild the Chroma store from scratch. It SHALL delete the existing `wiki/.chroma/` directory, enumerate all markdown files under `wiki/`, embed each one, and store the results in a new Chroma instance.

#### Scenario: Full rebuild
- **WHEN** the user runs `uv run wiki reindex`
- **THEN** the Chroma store is rebuilt from all current wiki pages, and the previous store is replaced
