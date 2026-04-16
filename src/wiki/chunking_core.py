"""Core chunk-splitting primitives shared by tools and ingest graphs."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from wiki.config import get_wiki_root


class RawChunk(BaseModel):
    """A mechanically derived source chunk."""

    chunk_id: str
    ordinal: int
    heading: str | None = None
    text: str
    word_count: int = Field(ge=0)
    source_path: str


def word_count(text: str) -> int:
    """Return a rough word count."""
    return len(text.split())


_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("chapter", re.compile(r"^(?=Chapter \d+.*)", re.MULTILINE)),
    ("heading", re.compile(r"^(?=#{1,3} \S)", re.MULTILINE)),
    ("stanza", re.compile(r"^(?=\*\*\*)", re.MULTILINE)),
]


def detect_sections(text: str) -> list[tuple[str, str]] | None:
    """Detect structural sections in text.

    Returns a list of ``(title, body)`` tuples if clear structure is found,
    otherwise ``None``.
    """
    for _kind, pattern in _SECTION_PATTERNS:
        splits = pattern.split(text)
        if len(splits) < 3:
            continue

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


def split_at_boundaries(text: str, chunk_size: int) -> list[str]:
    """Split text into roughly equal chunks at paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = word_count(para)
        if current and current_len + para_len > chunk_size:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        if para_len > chunk_size:
            turns = re.split(r"(?=^[\w\s]+:)", para, flags=re.MULTILINE)
            for turn in turns:
                turn = turn.strip()
                if not turn:
                    continue
                turn_len = word_count(turn)
                if current and current_len + turn_len > chunk_size:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0
                current.append(turn)
                current_len += turn_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def split_source_text(*, content: str, source_path: str, chunk_size: int) -> tuple[list[RawChunk], str]:
    """Split source text into raw chunks and report the method used."""
    sections = detect_sections(content)
    chunk_texts: list[tuple[str | None, str]] = []

    if sections:
        for title, body in sections:
            full_text = f"# {title}\n\n{body}" if body.strip() else title
            if word_count(full_text) <= int(chunk_size * 1.35):
                chunk_texts.append((title, full_text))
                continue

            for subchunk in split_at_boundaries(full_text, chunk_size):
                chunk_texts.append((title, subchunk))
        method = f"by sections ({len(sections)} sections detected)"
    else:
        chunk_texts = [(None, chunk) for chunk in split_at_boundaries(content, chunk_size)]
        method = f"by size ({chunk_size} words)"

    chunks = [
        RawChunk(
            chunk_id=f"chunk-{i:03d}",
            ordinal=i,
            heading=heading,
            text=text,
            word_count=word_count(text),
            source_path=source_path,
        )
        for i, (heading, text) in enumerate(chunk_texts, 1)
        if text.strip()
    ]
    return chunks, method


def load_source_chunks(path: str, chunk_size: int) -> tuple[Path, list[RawChunk], str, int]:
    """Read a source file from the wiki root and split it into raw chunks."""
    source_path = get_wiki_root() / path
    if not source_path.exists():
        raise FileNotFoundError(path)

    content = source_path.read_text(encoding="utf-8")
    total_words = word_count(content)
    chunks, method = split_source_text(content=content, source_path=path, chunk_size=chunk_size)
    return source_path, chunks, method, total_words
