"""Gorgeous Textual TUI for the wiki REPL.

Beautiful, responsive chat interface with:
- Rich markdown rendering for agent responses
- Live streaming with batched updates (~12fps)
- Thinking/reasoning blocks (dim, collapsible feel)
- Tool call indicators as inline badges
- Status bar with model info and turn counter

Usage::

    from wiki.tui import run_tui_chat, run_tui_ingest

    run_tui_chat(agent, config, model_name="gpt-5.4-mini")
    run_tui_ingest(agent, config, initial_messages, model_name="gpt-5.4-mini")
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll, Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Static

if TYPE_CHECKING:
    pass


# ── Stream parsing (shared logic with streaming.py) ─────────────────────


def _extract_thinking(chunk: object) -> str | None:
    """Extract reasoning/thinking text from a streaming chunk."""
    rc = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
    if rc and isinstance(rc, str):
        return rc or None

    content = getattr(chunk, "content", None)
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "reasoning" and "summary" in block:
            for s in block["summary"]:
                if isinstance(s, dict) and s.get("text"):
                    parts.append(s["text"])
        elif block.get("type") == "reasoning_content":
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "".join(parts) if parts else None


def _extract_content(chunk: object) -> str | None:
    """Extract normal text content from a streaming chunk."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "".join(parts) if parts else None
    return None


def _extract_tool_call(chunk: object) -> str | None:
    """Extract tool call name from a streaming chunk (returns name or None)."""
    tc_chunks = getattr(chunk, "tool_call_chunks", None)
    if tc_chunks:
        tc = tc_chunks[-1]
        if isinstance(tc, dict) and tc.get("name"):
            return tc["name"]
    return None


def iter_stream(event_stream: object):
    """Yield ``(event_type, data)`` tuples from an agent stream.

    Event types: ``"thinking"``, ``"content"``, ``"tool"``.
    """
    current_tool: str | None = None

    for event in event_stream:
        if not isinstance(event, tuple) or len(event) != 2:
            continue
        chunk, _ = event

        # Skip non-AI chunks early
        type_name = type(chunk).__name__
        if type_name != "AIMessageChunk":
            continue

        thinking = _extract_thinking(chunk)
        if thinking:
            yield "thinking", thinking
            continue

        text = _extract_content(chunk)
        if text:
            yield "content", text
            continue

        tool = _extract_tool_call(chunk)
        if tool and tool != current_tool:
            current_tool = tool
            yield "tool", tool


# ── TUI App ─────────────────────────────────────────────────────────────


class WikiReplApp(App):
    """Beautiful wiki REPL powered by Textual."""

    CSS = """
    Screen {
        background: #0d1117;
    }

    #message-log {
        height: 1fr;
        padding: 0 2;
        scrollbar-size: 1 1;
        scrollbar-background: #161b22;
        scrollbar-color: #30363d;
    }

    .welcome-banner {
        margin: 1 0 2 0;
    }

    .user-msg {
        margin: 1 0 0 0;
    }

    .assistant-msg {
        margin: 0 0 1 0;
    }

    .error-msg {
        margin: 1 0;
    }

    #input-bar {
        height: auto;
        dock: bottom;
        padding: 0 1;
        background: #161b22;
        border-top: tall #30363d;
    }

    Input {
        width: 100%;
        background: #0d1117;
        border: tall #30363d;
        padding: 1 2;
        color: #c9d1d9;
    }

    Input:focus {
        border: tall #58a6ff;
    }

    Input.-placeholder {
        color: #484f58;
    }

    Input .input--cursor {
        color: #58a6ff;
    }

    #status {
        dock: bottom;
        height: 1;
        width: 100%;
        background: #0d1117;
        color: #484f58;
        padding: 0 3;
        content-align: left middle;
        text-style: italic;
    }

    Header {
        background: #161b22;
        border-bottom: tall #30363d;
    }

    Footer {
        background: #161b22;
        border-top: tall #30363d;
    }

    Footer .footer--key {
        background: #30363d;
        color: #c9d1d9;
    }

    Footer .footer--description {
        color: #8b949e;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True),
    ]

    is_streaming: reactive[bool] = reactive(False)
    turn_count: reactive[int] = reactive(0)

    def __init__(
        self,
        agent: object,
        config: dict,
        *,
        mode: str = "chat",
        model_name: str = "unknown",
        initial_messages: list[dict] | None = None,
        shortcuts: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.agent = agent
        self.config = config
        self.mode = mode
        self.model_name = model_name
        self.initial_messages = initial_messages
        self.shortcuts = shortcuts or {}
        self._cancel = False

        # Streaming state (set per-turn)
        self._ast_widget: Static | None = None
        self._ast_thinking: str = ""
        self._ast_content: str = ""
        self._ast_tools: list[str] = []

    # ── Composition ─────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="message-log")
        yield Static("", id="status")
        yield Horizontal(
            Input(
                placeholder="Ask something… (Ctrl+Q quit · Ctrl+C interrupt)",
                id="user-input",
            ),
            id="input-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#user-input", Input).focus()
        self._update_status()

        # Welcome banner
        log = self.query_one("#message-log", VerticalScroll)
        title = "Wiki Ingest" if self.mode == "ingest" else "Wiki Chat"
        banner = Static(
            Panel(
                Text.from_markup(
                    "[bold cyan]⟁[/bold cyan]  "
                    f"[bold white]{title}[/bold white]"
                    f"  [dim]· {self.model_name}[/dim]\n\n"
                    "Ask questions about your wiki. Press [bold]Enter[/bold] to send.\n"
                    "Type [bold]exit[/bold] to quit."
                ),
                border_style="#30363d",
                padding=(1, 2),
            ),
            classes="welcome-banner",
        )
        log.mount(banner)

        # Ingest mode: auto-fire initial prompt
        if self.initial_messages:
            self._send_messages(self.initial_messages)

    # ── Input handling ──────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.is_streaming:
            return

        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.lower() in ("exit", "quit", "done"):
            self.exit()
            return

        # Resolve shortcuts (e.g. "go" → approval prompt in ingest mode)
        resolved = self.shortcuts.get(text.lower())
        if resolved:
            text = resolved

        self._send_user_message(text)

    def _send_user_message(self, text: str) -> None:
        """Append a user bubble and kick off streaming."""
        log = self.query_one("#message-log", VerticalScroll)
        log.mount(
            Static(
                Panel(
                    Text(text, style="#c9d1d9"),
                    title="👤  You",
                    title_align="left",
                    border_style="#58a6ff",
                    padding=(0, 1),
                    expand=True,
                ),
                classes="user-msg",
            )
        )
        log.scroll_end(animate=False)

        self.is_streaming = True
        self._update_status()
        self._run_stream_worker([{"role": "user", "content": text}])

    def _send_messages(self, messages: list[dict]) -> None:
        """Send a batch of messages (used for ingest initial prompt)."""
        # Display the last user message
        for m in reversed(messages):
            if m.get("role") == "user":
                log = self.query_one("#message-log", VerticalScroll)
                log.mount(
                    Static(
                        Panel(
                            Text(m["content"][:200], style="#c9d1d9"),
                            title="👤  Ingest Prompt",
                            title_align="left",
                            border_style="#58a6ff",
                            padding=(0, 1),
                            expand=True,
                        ),
                        classes="user-msg",
                    )
                )
                break

        self.is_streaming = True
        self._update_status()
        self._run_stream_worker(messages)

    # ── Streaming engine ────────────────────────────────────────────

    @work(thread=True, group="stream", exclusive=True)
    def _run_stream_worker(self, messages: list[dict]) -> None:
        """Consume the agent stream in a background thread, batch UI updates."""
        self._cancel = False

        # Prepare the assistant widget on the main thread
        self.call_from_thread(self._create_assistant_widget)

        event_stream = self.agent.stream(
            {"messages": messages},
            config=self.config,
            stream_mode="messages",
        )

        thinking_buf: list[str] = []
        content_buf: list[str] = []
        tools: list[str] = []
        last_flush = 0.0

        try:
            for event_type, data in iter_stream(event_stream):
                if self._cancel:
                    break

                if event_type == "thinking":
                    thinking_buf.append(data)
                elif event_type == "content":
                    content_buf.append(data)
                elif event_type == "tool":
                    tools.append(data)

                now = time.monotonic()
                if now - last_flush >= 0.08:  # ~12 fps
                    self.call_from_thread(
                        self._flush,
                        "".join(thinking_buf),
                        "".join(content_buf),
                        list(tools),
                    )
                    thinking_buf.clear()
                    content_buf.clear()
                    last_flush = now

        except Exception as exc:
            self.call_from_thread(self._show_error, str(exc))
            return

        # Final flush — always send whatever is left
        final_thinking = "".join(thinking_buf)
        final_content = "".join(content_buf)
        final_tools = list(tools)

        if self._cancel:
            final_content += "\n\n*[interrupted]*"

        self.call_from_thread(
            self._flush_final,
            final_thinking,
            final_content,
            final_tools,
        )

    def _create_assistant_widget(self) -> None:
        """Create a fresh assistant message widget and reset streaming state."""
        log = self.query_one("#message-log", VerticalScroll)
        self._ast_thinking = ""
        self._ast_content = ""
        self._ast_tools = []

        self._ast_widget = Static(
            Panel(
                Text("⠋ Thinking…", style="dim italic #484f58"),
                title="🤖  Wiki Agent",
                title_align="left",
                border_style="#3fb950",
                padding=(0, 1),
                expand=True,
            ),
            classes="assistant-msg",
        )
        log.mount(self._ast_widget)
        log.scroll_end(animate=False)

    def _flush(self, thinking_delta: str, content_delta: str, tools: list[str]) -> None:
        """Merge buffered tokens into the live assistant widget."""
        if thinking_delta:
            self._ast_thinking += thinking_delta
        if content_delta:
            self._ast_content += content_delta
        if tools:
            self._ast_tools = tools

        self._render_assistant()
        self.query_one("#message-log", VerticalScroll).scroll_end(animate=False)

    def _flush_final(self, thinking: str, content: str, tools: list[str]) -> None:
        """Final render + re-enable input."""
        if thinking:
            self._ast_thinking += thinking
        if content:
            self._ast_content += content
        if tools:
            self._ast_tools = tools

        self._render_assistant()
        self.query_one("#message-log", VerticalScroll).scroll_end(animate=False)

        self.is_streaming = False
        self.turn_count += 1
        self._update_status()
        self.query_one("#user-input", Input).focus()

    def _render_assistant(self) -> None:
        """Re-render the current assistant widget from accumulated state."""
        if self._ast_widget is None:
            return

        elements: list = []

        # ── Thinking block ──────────────────────────────────────
        if self._ast_thinking:
            display = self._ast_thinking
            # Keep the thinking block compact during streaming
            if len(display) > 600:
                display = display[-500:]
            elements.append(
                Panel(
                    Text(display, style="dim italic #484f58"),
                    title="💭 Thinking",
                    title_align="left",
                    border_style="#21262d",
                    padding=(0, 1),
                    expand=True,
                )
            )

        # ── Tool call badges ────────────────────────────────────
        if self._ast_tools:
            lines: list[str] = []
            for tc in dict.fromkeys(self._ast_tools):  # dedupe, preserve order
                lines.append(f"  ▸ {tc}()")
            elements.append(
                Text("\n".join(lines), style="bold #d29922")
            )

        # ── Main content (markdown) ─────────────────────────────
        if self._ast_content:
            elements.append(Markdown(self._ast_content))
        elif not self._ast_thinking and not self._ast_tools:
            elements.append(Text("▌", style="blink #3fb950"))

        inner = Group(*elements) if elements else Text("")

        self._ast_widget.update(
            Panel(
                inner,
                title="🤖  Wiki Agent",
                title_align="left",
                border_style="#3fb950",
                padding=(0, 1),
                expand=True,
            )
        )

    def _show_error(self, message: str) -> None:
        """Display an error message in the log."""
        log = self.query_one("#message-log", VerticalScroll)
        log.mount(
            Static(
                Panel(
                    Text(message, style="bold #f85149"),
                    title="⚠  Error",
                    title_align="left",
                    border_style="#f85149",
                    padding=(0, 1),
                    expand=True,
                ),
                classes="error-msg",
            )
        )
        log.scroll_end(animate=False)
        self.is_streaming = False
        self._update_status()

    # ── Actions ─────────────────────────────────────────────────────

    def action_interrupt(self) -> None:
        """Cancel the current stream."""
        if self.is_streaming:
            self._cancel = True

    # ── Status bar ──────────────────────────────────────────────────

    def _update_status(self) -> None:
        status = self.query_one("#status", Static)
        parts = [self.model_name, f"turn {self.turn_count}"]
        if self.is_streaming:
            parts.append("● streaming")
        status.update("  ·  ".join(parts))


# ── Public entry points ─────────────────────────────────────────────────


def run_tui_chat(
    agent: object,
    config: dict,
    *,
    model_name: str,
) -> None:
    """Launch the interactive chat TUI."""
    app = WikiReplApp(
        agent,
        config,
        mode="chat",
        model_name=model_name,
    )
    app.run()


def run_tui_ingest(
    agent: object,
    config: dict,
    initial_messages: list[dict],
    *,
    model_name: str,
    shortcuts: dict[str, str] | None = None,
) -> None:
    """Launch the ingest TUI (auto-sends *initial_messages* on start)."""
    app = WikiReplApp(
        agent,
        config,
        mode="ingest",
        model_name=model_name,
        initial_messages=initial_messages,
        shortcuts=shortcuts,
    )
    app.run()
