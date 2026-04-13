"""Streaming helpers for agent REPLs — shows thinking tokens live."""

from __future__ import annotations

from collections.abc import Iterator

from langchain_core.messages import AIMessageChunk, ToolMessage
from rich.console import Console

console = Console()


def _extract_thinking(chunk: AIMessageChunk) -> str | None:
    """Extract reasoning/thinking text from a streaming chunk.

    Handles multiple formats:
    - Responses API: content blocks with type='reasoning' + summary
    - Chat Completions API: additional_kwargs['reasoning_content']
    - Some providers: content blocks with type='reasoning_content'
    """
    # Chat Completions API reasoning comes via additional_kwargs
    rc = chunk.additional_kwargs.get("reasoning_content")
    if rc and isinstance(rc, str):
        return rc if rc else None

    if not isinstance(chunk.content, list):
        return None

    parts: list[str] = []
    for block in chunk.content:
        if isinstance(block, dict):
            # Responses API format: type=reasoning with summary text
            if block.get("type") == "reasoning" and "summary" in block:
                for summary_block in block["summary"]:
                    if isinstance(summary_block, dict) and summary_block.get("text"):
                        parts.append(summary_block["text"])
            # Some providers emit reasoning_content directly
            elif block.get("type") == "reasoning_content":
                text = block.get("text", "")
                if text:
                    parts.append(text)

    return "".join(parts) if parts else None


def _extract_content(chunk: AIMessageChunk) -> str | None:
    """Extract normal text content from a streaming chunk."""
    if isinstance(chunk.content, str):
        return chunk.content if chunk.content else None
    if isinstance(chunk.content, list):
        parts: list[str] = []
        for block in chunk.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "".join(parts) if parts else None
    return None


def _extract_tool_call(chunk: AIMessageChunk) -> dict | None:
    """Extract tool call info from a streaming chunk."""
    if chunk.tool_call_chunks:
        tc = chunk.tool_call_chunks[-1]
        if isinstance(tc, dict) and tc.get("name"):
            return {"name": tc["name"]}
    return None


def stream_agent_response(event_stream: Iterator, *, show_tools: bool = True) -> dict:
    """Consume a ``stream_mode="messages"`` event stream with live Rich output.

    Displays:
    - Thinking/reasoning tokens in dim gray
    - Content tokens in normal style
    - Tool calls as short bullet lines (if show_tools)

    Returns the final accumulated state's messages list (from the last
    "values"‑style event), or an empty dict if nothing was emitted.
    """
    thinking_buffer = ""
    content_buffer = ""
    current_tool: str | None = None
    in_thinking = False
    in_content = False

    for event in event_stream:
        # stream_mode="messages" yields (chunk, metadata) tuples
        if not isinstance(event, tuple) or len(event) != 2:
            continue

        chunk, metadata = event

        # We only care about AIMessageChunks for token streaming
        if not isinstance(chunk, AIMessageChunk):
            continue

        # --- Thinking / reasoning tokens ---
        thinking = _extract_thinking(chunk)
        if thinking:
            if not in_thinking:
                # Transition: close any open content block
                if in_content:
                    console.print()
                    in_content = False
                console.print("[dim italic]Thinking...[/dim italic]")
                in_thinking = True
            console.file.write(thinking)
            console.file.flush()
            thinking_buffer += thinking
            continue

        # --- Normal content tokens ---
        text = _extract_content(chunk)
        if text:
            if in_thinking:
                # Transition from thinking to content
                console.print("\n")
                in_thinking = False
            if not in_content:
                in_content = True
            console.file.write(text)
            console.file.flush()
            content_buffer += text
            continue

        # --- Tool call markers ---
        if show_tools:
            tc = _extract_tool_call(chunk)
            if tc:
                if in_thinking:
                    console.print("\n")
                    in_thinking = False
                if in_content:
                    console.print()
                    in_content = False
                name = tc["name"]
                if name != current_tool:
                    current_tool = name
                    console.print(f"  [dim]→ {name}()[/dim]")

        # --- Tool results (ToolMessage) are noisy, skip ---
        if isinstance(chunk, ToolMessage):
            continue

    # Ensure we end with a newline
    if in_thinking or in_content:
        console.print()

    return {"thinking": thinking_buffer, "content": content_buffer}
