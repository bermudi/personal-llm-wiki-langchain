# Chunking Pipeline

## ADDED Requirements

### Requirement: Mechanical Split

The `split_source` tool SHALL mechanically split a raw source into size-bounded chunks when the source exceeds a comfortable single-pass reading length (approximately 10,000 words). Splits SHALL occur at natural boundaries (paragraph breaks, speaker turns) where possible. Each chunk SHALL be roughly equal in size with no chunk exceeding the specified `chunk_size` (default ~5,000 words). Chunks SHALL be saved as individual files under `scratch/<source-slug>/chunk-NNN.md`.

#### Scenario: Two-hour podcast transcript (~25,000 words)
- **WHEN** the agent detects a long transcript and calls `split_source`
- **THEN** the source is split into 5-6 roughly equal chunks at paragraph or speaker-turn boundaries, saved to `scratch/<source-slug>/chunk-001.md` through `chunk-006.md`

#### Scenario: Short article (~2,000 words)
- **WHEN** the agent processes a source under the chunking threshold
- **THEN** the agent processes the source in full without invoking the chunking pipeline

### Requirement: Per-Chunk Extraction

For each chunk, the `extract_chunk` tool SHALL produce a structured extraction note containing: main topics discussed, entities and people mentioned, key claims and arguments, notable quotes, and unresolved questions or ambiguities. These notes SHALL be saved as individual files under `scratch/<source-slug>/chunk-NNN.md` (replacing the raw chunk content with the structured note).

#### Scenario: Extracting from a chunk
- **WHEN** the agent calls `extract_chunk("scratch/2026-04-13-podcast/chunk-003.md")`
- **THEN** a structured note is saved containing sections for topics, entities, claims, quotes, and questions

### Requirement: Cross-Chunk Grouping

After all chunks are extracted, the `group_chunks` tool SHALL compare chunk notes and group chunks that discuss semantically related topics, even if they are temporally distant in the source. The grouping identifies topic clusters that span multiple chunks.

#### Scenario: Recurring topic across segments
- **WHEN** chunk-001 discusses "institutional trust" at minute 10 and chunk-005 returns to "institutional trust" at minute 95
- **THEN** chunks 001 and 005 are grouped together under a "institutional trust" topic cluster

### Requirement: Final Synthesis Over Groups

The `synthesize_group` tool SHALL perform the final wiki update by working over each topic-linked chunk group, reading the relevant chunk notes and (if needed) the original source segments. Related content from across the source SHALL be synthesized together rather than processed in isolation.

#### Scenario: Synthesizing a topic cluster
- **WHEN** the agent processes the "institutional trust" cluster containing chunks 001 and 005
- **THEN** it reads both chunk notes and the relevant source segments, creates or updates wiki pages with a unified treatment, and notes the temporal span
