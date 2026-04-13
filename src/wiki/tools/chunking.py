"""Chunking pipeline tools for long source documents."""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import tool


def _content_to_str(content: str | list) -> str:
    """Normalize model response content to a plain string."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block["text"] if isinstance(block, dict) and "text" in block else str(block)
        for block in content
    )


def _word_count(text: str) -> int:
    """Rough word count."""
    return len(text.split())


# Patterns that indicate structural section breaks.
# Order matters — first match wins.
_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("chapter", re.compile(r"^(?=Chapter \d+.*)", re.MULTILINE)),
    ("heading", re.compile(r"^(?=#{1,3} \S)", re.MULTILINE)),
    ("stanza", re.compile(r"^(?=\*\*\*)", re.MULTILINE)),
]


def _detect_sections(text: str) -> list[tuple[str, str]] | None:
    """Detect structural sections in text.

    Returns a list of (title, body) tuples if sections are found,
    or None if no clear structure is detected (caller should fall
    back to size-based splitting).
    """
    for kind, pattern in _SECTION_PATTERNS:
        splits = pattern.split(text)
        # pattern.split with a lookahead keeps the delimiter attached
        # to the following segment, but the first element is preamble.
        if len(splits) < 3:
            continue  # need at least preamble + 2 sections

        sections: list[tuple[str, str]] = []
        for segment in splits:
            segment = segment.strip()
            if not segment:
                continue
            first_line = segment.split("\n", 1)[0].strip()
            body = segment[len(first_line):].strip() if "\n" in segment else ""
            sections.append((first_line, body))

        if len(sections) >= 2:
            return sections

    return None


def _split_at_boundaries(text: str, chunk_size: int) -> list[str]:
    """Split text into roughly equal chunks at paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = _word_count(para)
        # If adding this paragraph exceeds chunk_size and we already have content, flush
        if current and current_len + para_len > chunk_size:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        # If a single paragraph exceeds chunk_size, we need to split it further
        if para_len > chunk_size:
            # Try splitting at speaker turns (e.g., "Speaker Name:")
            turns = re.split(r"(?=^[\w\s]+:)", para, flags=re.MULTILINE)
            for turn in turns:
                turn = turn.strip()
                if not turn:
                    continue
                if current and current_len + _word_count(turn) > chunk_size:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0
                current.append(turn)
                current_len += _word_count(turn)
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


@tool
def split_source(path: str, chunk_size: int = 5000) -> str:
    """Split a long source document into chunks.

    Auto-detects structural sections (chapters, headings, stanzas).
    If sections are found, each section becomes its own chunk.
    Otherwise falls back to size-bounded splitting at paragraph boundaries.

    Each chunk is saved as a separate file in scratch/<source-slug>/chunk-NNN.md.

    Use this for sources over ~10,000 words. For shorter sources, process directly.

    Args:
        path: Path to the source file in raw/.
        chunk_size: Target word count per chunk (fallback only). Defaults to 5000.
    """
    source_path = Path.cwd() / path
    if not source_path.exists():
        return f"Error: Source file not found: {path}"

    content = source_path.read_text(encoding="utf-8")
    total_words = _word_count(content)

    if total_words <= chunk_size:
        return f"Source is only {total_words} words — no chunking needed. Process directly."

    # Derive slug from filename
    slug = source_path.stem
    chunk_dir = Path.cwd() / "scratch" / slug
    chunk_dir.mkdir(parents=True, exist_ok=True)

    # Try structural splitting first
    sections = _detect_sections(content)
    if sections:
        chunks = [f"# {title}\n\n{body}" for title, body in sections if body.strip()]
        method = f"by sections ({len(sections)} sections detected)"
    else:
        chunks = _split_at_boundaries(content, chunk_size)
        method = f"by size ({chunk_size} words)"

    chunk_paths = []
    for i, chunk_text in enumerate(chunks, 1):
        chunk_path = chunk_dir / f"chunk-{i:03d}.md"
        chunk_path.write_text(chunk_text, encoding="utf-8")
        chunk_paths.append(f"scratch/{slug}/chunk-{i:03d}.md")

    return (
        f"Split {total_words} words into {len(chunks)} chunks ({method}):\n"
        + "\n".join(chunk_paths)
    )


@tool
def extract_chunk(chunk_path: str) -> str:
    """Extract structured notes from a chunk.

    Reads the chunk, produces a structured extraction note with:
    - Main topics discussed
    - Entities and people mentioned
    - Key claims and arguments
    - Notable quotes
    - Unresolved questions

    The structured note replaces the raw chunk content.

    Args:
        chunk_path: Path to the chunk file (e.g., scratch/source-slug/chunk-001.md).
    """
    resolved = Path.cwd() / chunk_path
    if not resolved.exists():
        return f"Error: Chunk not found: {chunk_path}"

    content = resolved.read_text(encoding="utf-8")

    # Build extraction prompt and call LLM
    from wiki.config import build_model

    model = build_model()

    prompt = f"""Analyze the following text chunk and extract structured notes.

For each category, list items as bullet points. Be specific and use the original language where possible.

## Topics
(Main themes discussed)

## Entities
(People, organizations, places, works mentioned)

## Claims
(Key arguments, assertions, or conclusions)

## Quotes
(Notable direct quotes worth preserving)

## Questions
(Unresolved questions or ambiguities)

---
TEXT CHUNK:
{content}
"""
    response = model.invoke(prompt)
    extraction = _content_to_str(response.content)

    # Save the structured note back
    header = f"# Extraction: {resolved.name}\n\n"
    header += f"Source: {chunk_path}\n"
    header += f"Original word count: {len(content.split())}\n\n---\n\n"
    full_note = header + extraction

    resolved.write_text(full_note, encoding="utf-8")

    return f"Extracted structured notes from {chunk_path}. Topics, entities, claims, quotes, and questions identified."


@tool
def group_chunks(chunk_paths: str) -> str:
    """Group related chunks by semantic similarity.

    Takes a list of chunk paths, reads their extraction notes, and uses the LLM
    to identify topic clusters that may span temporally distant chunks.

    Args:
        chunk_paths: Comma-separated list of chunk file paths.
    """
    paths = [p.strip() for p in chunk_paths.split(",")]

    notes: dict[str, str] = {}
    for p in paths:
        resolved = Path.cwd() / p
        if not resolved.exists():
            return f"Error: Chunk not found: {p}"
        notes[p] = resolved.read_text(encoding="utf-8")

    # Build grouping prompt
    from wiki.config import build_model

    model = build_model()

    notes_text = ""
    for p, note in notes.items():
        notes_text += f"\n### {p}\n{note}\n"

    prompt = f"""Analyze these chunk extraction notes and group them by semantic topic.
Chunks discussing the same theme should be grouped together, even if they are temporally distant.

Output format — for each group, output:
## Group: <topic name>
- chunk-path-1
- chunk-path-2

---
{notes_text}
"""
    response = model.invoke(prompt)
    return _content_to_str(response.content)


@tool
def synthesize_group(group_chunks_desc: str) -> str:
    """Synthesize a topic group into unified wiki page content.

    Reads the chunk notes for the specified chunks and synthesizes them
    into coherent wiki page content that captures the topic across all chunks.

    Args:
        group_chunks_desc: Description of the group with chunk paths, one per line.
    """
    # Parse chunk paths from the description
    lines = group_chunks_desc.strip().split("\n")
    chunk_paths = [l.strip().lstrip("- ") for l in lines if l.strip() and not l.startswith("##")]

    notes: list[str] = []
    for p in chunk_paths:
        resolved = Path.cwd() / p
        if resolved.exists():
            notes.append(resolved.read_text(encoding="utf-8"))

    if not notes:
        return "Error: No valid chunk notes found for synthesis."

    from wiki.config import build_model

    model = build_model()

    prompt = f"""Synthesize the following chunk extraction notes into a unified wiki page.
Capture the topic across all chunks — note temporal spans if relevant.
Include specific claims, quotes, and unresolved questions.

Output a complete wiki page in markdown format with:
- Title (# heading)
- Context section
- Main content organized by subtopic
- Source references
- Unresolved questions (if any)

---
{''.join(notes)}
"""
    response = model.invoke(prompt)
    return _content_to_str(response.content)
