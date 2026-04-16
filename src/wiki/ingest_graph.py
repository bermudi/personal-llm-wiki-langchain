"""LangGraph workflow for long-source chunk review and draft synthesis."""

from __future__ import annotations

import json
import math
import re
import shutil
import textwrap
import time
from pathlib import Path
from typing import Literal, Protocol

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import TypedDict

from wiki.chunking_core import RawChunk, load_source_chunks
from wiki.config import build_embeddings, build_model, get_wiki_root
from wiki.observability import ObsStore


class ModelProtocol(Protocol):
    """Minimal model protocol used by the graph."""

    def invoke(self, input: str) -> object: ...


class EmbeddingsProtocol(Protocol):
    """Minimal embeddings protocol used by the graph."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class ChunkNeighbor(BaseModel):
    """Nearest-neighbor metadata for a single chunk."""

    chunk_id: str
    score: float = Field(ge=-1.0, le=1.0)


class ChunkRelationship(BaseModel):
    """Embedding-derived relationship summary for a chunk."""

    chunk_id: str
    top_neighbors: list[ChunkNeighbor]
    previous_neighbor_score: float | None = None
    next_neighbor_score: float | None = None


class ChunkSummary(BaseModel):
    """Compact summary emitted for each chunk."""

    chunk_id: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    mixed_topics: bool = False
    split_recommendation: Literal["keep", "split", "merge"] = "keep"
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class CandidateGroup(BaseModel):
    """Deterministic candidate group derived from embeddings."""

    group_id: str
    chunk_ids: list[str]
    rationale: str
    average_similarity: float = Field(default=0.0, ge=-1.0, le=1.0)


class ReviewedGroup(BaseModel):
    """LLM-reviewed chunk grouping for synthesis."""

    title_hint: str
    chunk_ids: list[str]
    rationale: str
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class ReviewDecision(BaseModel):
    """High-level graph decision after reviewing chunk summaries + neighbors."""

    decision: Literal["accept", "retry_split"]
    review_notes: list[str] = Field(default_factory=list)
    groups: list[ReviewedGroup] = Field(default_factory=list)
    retry_reason: str | None = None
    focus_chunk_ids: list[str] = Field(default_factory=list)


class PageDraft(BaseModel):
    """Draft wiki page synthesized from a reviewed chunk group."""

    title_hint: str
    slug: str
    chunk_ids: list[str]
    draft_markdown: str
    rationale: str


class ChunkReviewResult(BaseModel):
    """Final result returned by the chunk review graph."""

    source_path: str
    attempt: int
    final_chunk_size: int
    chunk_count: int
    decision: Literal["accept", "retry_split"]
    artifact_dir: str
    review_notes: list[str]
    draft_paths: list[str]
    group_titles: list[str]


class ChunkReviewState(TypedDict):
    """Shared state for the chunk review graph."""

    source_path: str
    chunk_size: int
    min_chunk_size: int
    max_retries: int
    attempt: int
    source_slug: str
    artifact_root: str
    artifact_dir: str
    split_method: str
    total_words: int
    chunks: list[RawChunk]
    relationships: list[ChunkRelationship]
    candidate_groups: list[CandidateGroup]
    summaries: list[ChunkSummary]
    review: ReviewDecision | None
    page_drafts: list[PageDraft]
    # Observability
    run_id: str
    obs_store: ObsStore | None
    _model_turn: int  # internal counter


def _content_to_str(content: object) -> str:
    """Normalize model response content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _invoke_text(model: ModelProtocol, prompt: str) -> str:
    """Invoke the model and normalize the textual response."""
    response = model.invoke(prompt)
    content = getattr(response, "content", response)
    return _content_to_str(content).strip()


def _obs_invoke_text(
    model: ModelProtocol,
    prompt: str,
    *,
    run_id: str,
    obs_store: ObsStore | None,
    turn: int,
    node_name: str,
    tools_available: list[str] | None = None,
) -> str:
    """Invoke the model, log to SQLite, and return the textual response."""
    t0 = time.monotonic()
    response = model.invoke(prompt)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    raw_content = getattr(response, "content", response)
    resp_text = _content_to_str(raw_content).strip()

    # Extract reasoning if present
    reasoning = None
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                for s in block.get("summary", []):
                    if isinstance(s, dict) and s.get("text"):
                        parts.append(s["text"])
        if parts:
            reasoning = "".join(parts)
    if not reasoning and hasattr(response, "additional_kwargs"):
        rc = response.additional_kwargs.get("reasoning_content")
        if rc:
            reasoning = str(rc)

    # Extract usage
    usage = None
    usage_meta = getattr(response, "usage_metadata", None)
    if usage_meta:
        usage = dict(usage_meta) if isinstance(usage_meta, dict) else vars(usage_meta)

    if obs_store is not None:
        # Truncate large prompts for DB
        prompt_for_db = prompt
        if len(prompt_for_db) > 100_000:
            prompt_for_db = prompt_for_db[:100_000] + "\n... [truncated]"
        resp_for_db = resp_text
        if len(resp_for_db) > 100_000:
            resp_for_db = resp_for_db[:100_000] + "\n... [truncated]"
        reasoning_for_db = reasoning
        if reasoning_for_db and len(reasoning_for_db) > 100_000:
            reasoning_for_db = reasoning_for_db[:100_000] + "\n... [truncated]"

        obs_store.insert_model_call(
            run_id=run_id,
            turn=turn,
            system_msg=None,
            messages_in=[{"role": "user", "content": prompt_for_db}],
            tools_available=tools_available or [],
            response=resp_for_db,
            reasoning=reasoning_for_db,
            tool_calls=None,
            usage=usage,
            duration_ms=elapsed_ms,
        )
        obs_store.insert_message(
            run_id=run_id,
            role="user",
            content=f"[{node_name}] " + prompt_for_db[:10_000],
        )
        obs_store.insert_message(
            run_id=run_id,
            role="assistant",
            content=resp_for_db[:10_000],
        )

    return resp_text


def _obs_embed(
    embeddings: EmbeddingsProtocol,
    texts: list[str],
    *,
    run_id: str,
    obs_store: ObsStore | None,
    turn: int,
) -> list[list[float]]:
    """Embed texts, log to SQLite, and return vectors."""
    t0 = time.monotonic()
    vectors = embeddings.embed_documents(texts)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if obs_store is not None:
        obs_store.insert_tool_call(
            run_id=run_id,
            turn=turn,
            tool_call_id=None,
            tool_name="embed_documents",
            arguments={"text_count": len(texts), "total_chars": sum(len(t) for t in texts)},
            result=f"Embedded {len(texts)} texts into {len(vectors)} vectors in {elapsed_ms}ms",
            duration_ms=elapsed_ms,
        )

    return vectors


def _extract_json_blob(text: str) -> dict:
    """Extract the first JSON object from a model response."""
    text = text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _slugify(value: str) -> str:
    """Convert a string to a wiki-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _chunk_by_id(chunks: list[RawChunk]) -> dict[str, RawChunk]:
    """Index chunks by chunk id."""
    return {chunk.chunk_id: chunk for chunk in chunks}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _attempt_dir(state: ChunkReviewState) -> Path:
    """Directory for the current graph attempt."""
    return Path(state["artifact_root"]) / f"attempt-{state['attempt']:02d}"


def _reset_attempt_dir(path: Path) -> None:
    """Ensure the attempt directory starts clean."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: BaseModel | dict | list) -> None:
    """Write JSON payloads to disk with indentation."""
    if isinstance(payload, BaseModel):
        content = payload.model_dump_json(indent=2)
    else:
        content = json.dumps(payload, indent=2, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def _write_chunks(attempt_dir: Path, chunks: list[RawChunk]) -> None:
    """Persist raw chunks for inspection."""
    chunk_dir = attempt_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for chunk in chunks:
        heading = f"# {chunk.heading}\n\n" if chunk.heading and not chunk.text.startswith("# ") else ""
        (chunk_dir / f"{chunk.chunk_id}.md").write_text(heading + chunk.text, encoding="utf-8")


def _build_candidate_groups(chunks: list[RawChunk], vectors: list[list[float]]) -> tuple[list[ChunkRelationship], list[CandidateGroup]]:
    """Build neighbor metadata and simple connected-component clusters."""
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    score_map: dict[tuple[str, str], float] = {}

    for i, chunk in enumerate(chunks):
        for j in range(i + 1, len(chunks)):
            other = chunks[j]
            score = _cosine_similarity(vectors[i], vectors[j])
            score_map[(chunk.chunk_id, other.chunk_id)] = score
            score_map[(other.chunk_id, chunk.chunk_id)] = score

    relationships: list[ChunkRelationship] = []
    adjacency: dict[str, set[str]] = {chunk_id: set() for chunk_id in chunk_ids}

    def score(a: str, b: str) -> float:
        return score_map.get((a, b), 0.0)

    for index, chunk in enumerate(chunks):
        ranked = sorted(
            (
                ChunkNeighbor(chunk_id=other.chunk_id, score=score(chunk.chunk_id, other.chunk_id))
                for other in chunks
                if other.chunk_id != chunk.chunk_id
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        relationships.append(
            ChunkRelationship(
                chunk_id=chunk.chunk_id,
                top_neighbors=ranked[:3],
                previous_neighbor_score=score(chunk.chunk_id, chunks[index - 1].chunk_id) if index > 0 else None,
                next_neighbor_score=score(chunk.chunk_id, chunks[index + 1].chunk_id) if index + 1 < len(chunks) else None,
            )
        )

        for other in chunks:
            if other.chunk_id == chunk.chunk_id:
                continue
            pair_score = score(chunk.chunk_id, other.chunk_id)
            is_adjacent = abs(chunk.ordinal - other.ordinal) == 1
            if pair_score >= 0.83 or (is_adjacent and pair_score >= 0.74):
                adjacency[chunk.chunk_id].add(other.chunk_id)
                adjacency[other.chunk_id].add(chunk.chunk_id)

    components: list[list[str]] = []
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        stack = [chunk_id]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(sorted(adjacency[current] - seen))
        components.append(sorted(component, key=lambda cid: _chunk_ordinal(chunks, cid)))

    groups: list[CandidateGroup] = []
    for index, component in enumerate(sorted(components, key=lambda ids: _chunk_ordinal(chunks, ids[0])), 1):
        internal_scores: list[float] = []
        for i, chunk_id in enumerate(component):
            for other_id in component[i + 1:]:
                internal_scores.append(score(chunk_id, other_id))
        avg = sum(internal_scores) / len(internal_scores) if internal_scores else 0.0
        groups.append(
            CandidateGroup(
                group_id=f"group-{index:02d}",
                chunk_ids=component,
                rationale=(
                    "Strong embedding neighborhood" if len(component) > 1 else "Chunk appears semantically self-contained"
                ),
                average_similarity=avg,
            )
        )

    return relationships, groups


def _chunk_ordinal(chunks: list[RawChunk], chunk_id: str) -> int:
    """Return a chunk ordinal by id."""
    return _chunk_by_id(chunks)[chunk_id].ordinal


def _summary_prompt(chunk: RawChunk) -> str:
    """Prompt for structured chunk summarization."""
    return textwrap.dedent(
        f"""\
        TASK: CHUNK_SUMMARY_JSON

        Summarize this source chunk into compact JSON.
        Return exactly one JSON object with keys:
        - summary: string
        - topics: array of short strings
        - entities: array of short strings
        - claims: array of short strings
        - quotes: array of short strings (0-3 items)
        - mixed_topics: boolean
        - split_recommendation: one of [\"keep\", \"split\", \"merge\"]
        - confidence: number between 0 and 1

        chunk_id: {chunk.chunk_id}
        source_path: {chunk.source_path}
        heading: {chunk.heading or 'none'}
        word_count: {chunk.word_count}

        TEXT:
        {chunk.text}
        """
    )


def _fallback_summary(chunk: RawChunk) -> ChunkSummary:
    """Heuristic fallback if the model fails to emit valid JSON."""
    words = chunk.text.split()
    excerpt = " ".join(words[:40])
    return ChunkSummary(
        chunk_id=chunk.chunk_id,
        summary=excerpt + ("..." if len(words) > 40 else ""),
        topics=[],
        entities=[],
        claims=[],
        quotes=[],
        mixed_topics=False,
        split_recommendation="keep",
        confidence=0.35,
    )


def _review_prompt(
    *,
    state: ChunkReviewState,
    summaries: list[ChunkSummary],
    relationships: list[ChunkRelationship],
    candidate_groups: list[CandidateGroup],
) -> str:
    """Prompt for reviewing cluster coherence and retry decisions."""
    summary_map = {summary.chunk_id: summary for summary in summaries}
    relationship_map = {item.chunk_id: item for item in relationships}

    chunk_blocks: list[str] = []
    for chunk in state["chunks"]:
        summary = summary_map[chunk.chunk_id]
        rel = relationship_map[chunk.chunk_id]
        neighbors = ", ".join(f"{n.chunk_id}:{n.score:.2f}" for n in rel.top_neighbors) or "none"
        chunk_blocks.append(
            textwrap.dedent(
                f"""\
                - {chunk.chunk_id} (ordinal={chunk.ordinal}, words={chunk.word_count})
                  summary: {summary.summary}
                  topics: {', '.join(summary.topics) or 'none'}
                  mixed_topics: {summary.mixed_topics}
                  split_recommendation: {summary.split_recommendation}
                  neighbors: {neighbors}
                  prev_score: {rel.previous_neighbor_score}
                  next_score: {rel.next_neighbor_score}
                """
            ).strip()
        )

    group_blocks = [
        f"- {group.group_id}: chunks={', '.join(group.chunk_ids)} | avg_similarity={group.average_similarity:.2f} | {group.rationale}"
        for group in candidate_groups
    ]

    chunks_text = "\n".join(chunk_blocks)
    groups_text = "\n".join(group_blocks) if group_blocks else "- none"

    return textwrap.dedent(
        f"""\
        TASK: GROUP_REVIEW_JSON

        You are reviewing a long-source chunking plan.
        Decide whether the current split is good enough to synthesize pages, or whether the source should be re-split more finely.

        Return exactly one JSON object with keys:
        - decision: one of [\"accept\", \"retry_split\"]
        - review_notes: array of short strings
        - groups: array of objects with keys [title_hint, chunk_ids, rationale, confidence]
        - retry_reason: string or null
        - focus_chunk_ids: array of chunk ids that need special attention

        Guidance:
        - Prefer accept when chunks are coherent enough to synthesize quality page drafts.
        - Use retry_split when multiple chunks are marked mixed_topics=true, candidate groups look incoherent, or chunk boundaries are obviously too coarse.
        - It is okay for one group to contain 1 chunk and another to contain 3-4 chunks.
        - Preserve source order unless there is a strong semantic reason not to.

        source_path: {state['source_path']}
        attempt: {state['attempt']}
        chunk_size: {state['chunk_size']}
        split_method: {state['split_method']}

        CHUNKS:
        {chunks_text}

        CANDIDATE_GROUPS:
        {groups_text}
        """
    )


def _fallback_review(state: ChunkReviewState) -> ReviewDecision:
    """Fallback review: accept deterministic candidate groups."""
    groups = [
        ReviewedGroup(
            title_hint=group.group_id,
            chunk_ids=group.chunk_ids,
            rationale=group.rationale,
            confidence=0.5,
        )
        for group in state["candidate_groups"]
    ]
    return ReviewDecision(
        decision="accept",
        review_notes=["Fell back to embedding-derived groups because the model response was invalid."],
        groups=groups,
        retry_reason=None,
        focus_chunk_ids=[],
    )


def _synthesis_prompt(group: ReviewedGroup, chunks: list[RawChunk], summaries: list[ChunkSummary]) -> str:
    """Prompt for synthesizing a page draft from grouped chunks."""
    summary_by_id = {summary.chunk_id: summary for summary in summaries}
    ordered_chunks = sorted(chunks, key=lambda item: item.ordinal)
    chunk_blocks: list[str] = []
    for chunk in ordered_chunks:
        summary = summary_by_id[chunk.chunk_id]
        chunk_blocks.append(
            textwrap.dedent(
                f"""\
                ## {chunk.chunk_id}
                Summary: {summary.summary}
                Topics: {', '.join(summary.topics) or 'none'}
                Claims: {', '.join(summary.claims) or 'none'}
                Quotes: {' | '.join(summary.quotes) or 'none'}

                RAW TEXT:
                {chunk.text}
                """
            ).strip()
        )

    material_text = "\n\n".join(chunk_blocks)

    return textwrap.dedent(
        f"""\
        TASK: SYNTHESIZE_GROUP_PAGE

        Write a complete wiki page in markdown for this chunk group.
        Requirements:
        - Start with a level-1 title
        - Include sections: Context, Analysis, Source references
        - Be specific, grounded, and cite chunk ids in the source references section
        - Do not mention vectors, embeddings, or clustering in the final page

        title_hint: {group.title_hint}
        rationale: {group.rationale}
        chunk_ids: {', '.join(group.chunk_ids)}

        MATERIAL:
        {material_text}
        """
    )


def _fallback_draft(group: ReviewedGroup, chunks: list[RawChunk], summaries: list[ChunkSummary]) -> str:
    """Fallback page draft if synthesis model output is poor."""
    summary_by_id = {summary.chunk_id: summary for summary in summaries}
    lines = [f"# {group.title_hint.title()}", "", "## Context", "", group.rationale, "", "## Analysis", ""]
    for chunk in sorted(chunks, key=lambda item: item.ordinal):
        summary = summary_by_id[chunk.chunk_id]
        lines.append(f"### {chunk.chunk_id}")
        lines.append(summary.summary)
        if summary.claims:
            lines.append("")
            lines.append("Claims:")
            lines.extend(f"- {claim}" for claim in summary.claims)
        lines.append("")
    lines.extend(["## Source references", ""])
    lines.extend(f"- {chunk.chunk_id} ({chunk.source_path})" for chunk in sorted(chunks, key=lambda item: item.ordinal))
    lines.append("")
    return "\n".join(lines)


def build_chunk_review_graph(
    *,
    model: ModelProtocol | None = None,
    embeddings: EmbeddingsProtocol | None = None,
):
    """Build the long-source chunk review LangGraph."""
    model = model or build_model()
    embeddings = embeddings or build_embeddings()

    def prepare_chunks(state: ChunkReviewState) -> dict:
        source_path, chunks, method, total_words = load_source_chunks(state["source_path"], state["chunk_size"])
        attempt_dir = _attempt_dir(state)
        _reset_attempt_dir(attempt_dir)
        _write_chunks(attempt_dir, chunks)
        manifest = {
            "source_path": state["source_path"],
            "chunk_size": state["chunk_size"],
            "split_method": method,
            "total_words": total_words,
            "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        }
        _write_json(attempt_dir / "chunk-manifest.json", manifest)
        return {
            "artifact_dir": str(attempt_dir),
            "split_method": method,
            "total_words": total_words,
            "chunks": chunks,
            "relationships": [],
            "candidate_groups": [],
            "summaries": [],
            "review": None,
            "page_drafts": [],
        }

    def embed_and_cluster(state: ChunkReviewState) -> dict:
        turn = (state.get("_model_turn", 0) or 0) + 1
        texts = [chunk.text for chunk in state["chunks"]]
        vectors = _obs_embed(
            embeddings, texts,
            run_id=state["run_id"],
            obs_store=state.get("obs_store"),
            turn=turn,
        )
        relationships, candidate_groups = _build_candidate_groups(state["chunks"], vectors)
        _write_json(Path(state["artifact_dir"]) / "neighbors.json", [item.model_dump(mode="json") for item in relationships])
        _write_json(
            Path(state["artifact_dir"]) / "candidate-groups.json",
            [item.model_dump(mode="json") for item in candidate_groups],
        )
        return {
            "relationships": relationships,
            "candidate_groups": candidate_groups,
            "_model_turn": turn,
        }

    def summarize_chunks(state: ChunkReviewState) -> dict:
        summaries: list[ChunkSummary] = []
        summary_dir = Path(state["artifact_dir"]) / "summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        base_turn = (state.get("_model_turn", 0) or 0)
        for chunk in state["chunks"]:
            prompt = _summary_prompt(chunk)
            turn = base_turn + len(summaries) + 1
            try:
                raw = _obs_invoke_text(
                    model, prompt,
                    run_id=state["run_id"],
                    obs_store=state.get("obs_store"),
                    turn=turn,
                    node_name="summarize_chunks",
                )
                payload = _extract_json_blob(raw)
                summary = ChunkSummary(chunk_id=chunk.chunk_id, **payload)
            except (ValidationError, json.JSONDecodeError, TypeError, ValueError):
                summary = _fallback_summary(chunk)
            summaries.append(summary)
            _write_json(summary_dir / f"{chunk.chunk_id}.json", summary)
        return {
            "summaries": summaries,
            "_model_turn": base_turn + len(summaries),
        }

    def review_groups(state: ChunkReviewState) -> dict:
        turn = (state.get("_model_turn", 0) or 0) + 1
        prompt = _review_prompt(
            state=state,
            summaries=state["summaries"],
            relationships=state["relationships"],
            candidate_groups=state["candidate_groups"],
        )
        try:
            raw = _obs_invoke_text(
                model, prompt,
                run_id=state["run_id"],
                obs_store=state.get("obs_store"),
                turn=turn,
                node_name="review_groups",
            )
            payload = _extract_json_blob(raw)
            review = ReviewDecision(**payload)
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError):
            review = _fallback_review(state)
        _write_json(Path(state["artifact_dir"]) / "review.json", review)
        return {
            "review": review,
            "_model_turn": turn,
        }

    def route_after_review(state: ChunkReviewState) -> Literal["refine_chunks", "synthesize_pages"]:
        review = state["review"]
        if review is None:
            return "synthesize_pages"
        if review.decision == "retry_split" and state["attempt"] < state["max_retries"]:
            return "refine_chunks"
        return "synthesize_pages"

    def refine_chunks(state: ChunkReviewState) -> dict:
        next_chunk_size = max(state["min_chunk_size"], int(state["chunk_size"] * 0.65))
        return {
            "attempt": state["attempt"] + 1,
            "chunk_size": next_chunk_size,
        }

    def synthesize_pages(state: ChunkReviewState) -> dict:
        review = state["review"] or _fallback_review(state)
        chunk_map = _chunk_by_id(state["chunks"])
        drafts_dir = Path(state["artifact_dir"]) / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        page_drafts: list[PageDraft] = []
        base_turn = (state.get("_model_turn", 0) or 0)
        for i, group in enumerate(review.groups):
            grouped_chunks = [chunk_map[chunk_id] for chunk_id in group.chunk_ids if chunk_id in chunk_map]
            if not grouped_chunks:
                continue
            prompt = _synthesis_prompt(group, grouped_chunks, state["summaries"])
            turn = base_turn + i + 1
            draft_markdown = _obs_invoke_text(
                model, prompt,
                run_id=state["run_id"],
                obs_store=state.get("obs_store"),
                turn=turn,
                node_name="synthesize_pages",
            )
            if not draft_markdown.strip().startswith("# "):
                draft_markdown = _fallback_draft(group, grouped_chunks, state["summaries"])
            slug = _slugify(group.title_hint)
            draft = PageDraft(
                title_hint=group.title_hint,
                slug=slug,
                chunk_ids=group.chunk_ids,
                draft_markdown=draft_markdown.strip() + "\n",
                rationale=group.rationale,
            )
            page_drafts.append(draft)
            (drafts_dir / f"{slug}.md").write_text(draft.draft_markdown, encoding="utf-8")

        _write_json(Path(state["artifact_dir"]) / "page-plan.json", [draft.model_dump(mode="json") for draft in page_drafts])
        return {
            "page_drafts": page_drafts,
            "_model_turn": base_turn + len(review.groups),
        }

    builder = StateGraph(ChunkReviewState)
    builder.add_node("prepare_chunks", prepare_chunks)
    builder.add_node("embed_and_cluster", embed_and_cluster)
    builder.add_node("summarize_chunks", summarize_chunks)
    builder.add_node("review_groups", review_groups)
    builder.add_node("refine_chunks", refine_chunks)
    builder.add_node("synthesize_pages", synthesize_pages)

    builder.add_edge(START, "prepare_chunks")
    builder.add_edge("prepare_chunks", "embed_and_cluster")
    builder.add_edge("embed_and_cluster", "summarize_chunks")
    builder.add_edge("summarize_chunks", "review_groups")
    builder.add_conditional_edges("review_groups", route_after_review, ["refine_chunks", "synthesize_pages"])
    builder.add_edge("refine_chunks", "prepare_chunks")
    builder.add_edge("synthesize_pages", END)
    return builder.compile()


def run_chunk_review_graph(
    *,
    path: str,
    chunk_size: int = 1500,
    max_retries: int = 1,
    model: ModelProtocol | None = None,
    embeddings: EmbeddingsProtocol | None = None,
    obs_store: ObsStore | None = None,
    run_id: str | None = None,
) -> ChunkReviewResult:
    """Run the long-source chunk review graph and return final artifact metadata.

    If *obs_store* is provided, every LLM call, embedding call, and message
    is logged to SQLite for deep observability.  If omitted, the graph runs
    without telemetry (useful in tests).
    """
    source = get_wiki_root() / path
    if not source.exists():
        raise FileNotFoundError(path)

    source_slug = source.stem
    artifact_root = get_wiki_root() / "scratch" / source_slug / "chunk-review"
    artifact_root.mkdir(parents=True, exist_ok=True)

    # Register the run in obs if a store was given
    if obs_store is not None and run_id is None:
        import uuid
        run_id = uuid.uuid4().hex
    if run_id is None:
        run_id = ""

    if obs_store is not None and run_id:
        from wiki.config import get_model_name, get_reasoning_effort

        obs_store.insert_run(
            run_id=run_id,
            thread_id=f"chunk-review-{source_slug}",
            command="chunk-review",
            model=get_model_name(),
            reasoning_effort=get_reasoning_effort(),
        )

    graph = build_chunk_review_graph(model=model, embeddings=embeddings)
    final_state = graph.invoke(
        {
            "source_path": path,
            "chunk_size": chunk_size,
            "min_chunk_size": max(350, chunk_size // 3),
            "max_retries": max_retries,
            "attempt": 1,
            "source_slug": source_slug,
            "artifact_root": str(artifact_root),
            "artifact_dir": "",
            "split_method": "",
            "total_words": 0,
            "chunks": [],
            "relationships": [],
            "candidate_groups": [],
            "summaries": [],
            "review": None,
            "page_drafts": [],
            # Observability
            "run_id": run_id,
            "obs_store": obs_store,
            "_model_turn": 0,
        }
    )

    review = final_state["review"] or _fallback_review(final_state)
    result = ChunkReviewResult(
        source_path=path,
        attempt=final_state["attempt"],
        final_chunk_size=final_state["chunk_size"],
        chunk_count=len(final_state["chunks"]),
        decision=review.decision,
        artifact_dir=final_state["artifact_dir"],
        review_notes=review.review_notes,
        draft_paths=[
            str(Path(final_state["artifact_dir"]) / "drafts" / f"{draft.slug}.md")
            for draft in final_state["page_drafts"]
        ],
        group_titles=[draft.title_hint for draft in final_state["page_drafts"]],
    )
    _write_json(Path(final_state["artifact_dir"]) / "result.json", result)
    return result
