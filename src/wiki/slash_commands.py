"""Shared slash-command parsing and dispatch for interactive transports."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

TransportName = Literal["chat", "telegram"]
SlashAction = Literal["none", "reset-thread", "exit-app"]


@dataclass(frozen=True, slots=True)
class SlashCommandContext:
    """Transport-agnostic context passed to slash command handlers."""

    transport: TransportName
    wiki_dir: Path
    thread_id: str
    model_name: str
    chat_base_url: str
    reasoning_effort: str | None
    use_responses_api: bool
    session_id: str | None = None
    active_epoch: int | None = None
    help_footer: str | None = None


@dataclass(frozen=True, slots=True)
class SlashCommandResult:
    """Result returned by a slash-command handler."""

    reply: str
    action: SlashAction = "none"
    error: bool = False


SlashHandler = Callable[["SlashCommandRegistry", SlashCommandContext, str], SlashCommandResult]


@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    """Command metadata + handler."""

    name: str
    description: str
    handler: SlashHandler
    aliases: tuple[str, ...] = ()
    transports: tuple[TransportName, ...] = ("chat", "telegram")

    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def supports(self, transport: TransportName) -> bool:
        return transport in self.transports


@dataclass(slots=True)
class SlashCommandRegistry:
    """Registry and dispatcher for slash commands."""

    _commands: dict[str, SlashCommandSpec] = field(default_factory=dict)
    _registration_order: list[SlashCommandSpec] = field(default_factory=list)

    def register(self, spec: SlashCommandSpec) -> None:
        for name in spec.all_names():
            key = name.lower()
            existing = self._commands.get(key)
            if existing is not None:
                raise ValueError(f"Slash command '/{key}' already registered")
            self._commands[key] = spec
        self._registration_order.append(spec)

    def available_commands(self, transport: TransportName) -> list[SlashCommandSpec]:
        return [spec for spec in self._registration_order if spec.supports(transport)]

    def dispatch(self, text: str, context: SlashCommandContext) -> SlashCommandResult | None:
        parsed = self.parse(text)
        if parsed is None:
            return None

        command_name, args = parsed
        spec = self._commands.get(command_name)
        if spec is None or not spec.supports(context.transport):
            return SlashCommandResult(
                reply=f"Unknown command '/{command_name}'. Try /help.",
                error=True,
            )
        return spec.handler(self, context, args)

    @staticmethod
    def parse(text: str) -> tuple[str, str] | None:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None

        body = stripped[1:].strip()
        if not body:
            return "", ""

        token, _, args = body.partition(" ")
        command_name = token.split("@", 1)[0].lower()
        return command_name, args.strip()


def build_shared_slash_registry() -> SlashCommandRegistry:
    registry = SlashCommandRegistry()
    registry.register(
        SlashCommandSpec(
            name="help",
            aliases=("start",),
            description="Show available slash commands.",
            handler=_handle_help,
        )
    )
    registry.register(
        SlashCommandSpec(
            name="status",
            description="Show wiki status and the active session thread.",
            handler=_handle_status,
        )
    )
    registry.register(
        SlashCommandSpec(
            name="model",
            description="Show the active chat model configuration.",
            handler=_handle_model,
        )
    )
    registry.register(
        SlashCommandSpec(
            name="new",
            aliases=("reset", "clear"),
            description="Start a fresh conversation thread.",
            handler=_handle_new,
        )
    )
    return registry


def build_chat_slash_registry() -> SlashCommandRegistry:
    registry = build_shared_slash_registry()
    registry.register(
        SlashCommandSpec(
            name="exit",
            aliases=("quit",),
            description="Quit the chat app.",
            handler=_handle_exit,
            transports=("chat",),
        )
    )
    return registry


def build_telegram_slash_registry() -> SlashCommandRegistry:
    return build_shared_slash_registry()


def _handle_help(registry: SlashCommandRegistry, context: SlashCommandContext, args: str) -> SlashCommandResult:
    del args
    lines = ["Wiki slash commands", ""]
    for spec in registry.available_commands(context.transport):
        aliases = [alias for alias in spec.aliases if registry._commands.get(alias) is spec]
        alias_suffix = f" ({', '.join(f'/{alias}' for alias in aliases)})" if aliases else ""
        lines.append(f"/{spec.name}{alias_suffix} — {spec.description}")

    if context.help_footer:
        lines.extend(["", context.help_footer.strip()])

    return SlashCommandResult("\n".join(lines))


def _handle_status(registry: SlashCommandRegistry, context: SlashCommandContext, args: str) -> SlashCommandResult:
    del registry, args

    wiki_pages = _count_files(context.wiki_dir / "wiki", pattern="*.md", exclude={"index.md", "log.md"})
    raw_sources = _count_all_files(context.wiki_dir / "raw")
    scratch_files = _count_all_files(context.wiki_dir / "scratch")
    chroma_dir = context.wiki_dir / "wiki" / ".chroma"
    chroma_state = "present" if chroma_dir.exists() else "missing"
    git_state = _git_summary(context.wiki_dir)

    lines = [
        "Wiki status",
        "",
        f"Transport: {context.transport}",
    ]

    if context.session_id:
        lines.append(f"Session: {context.session_id}")
    if context.active_epoch is not None:
        lines.append(f"Epoch: {context.active_epoch}")

    lines.extend(
        [
            f"Thread: {context.thread_id}",
            f"Pages: {wiki_pages}",
            f"Raw sources: {raw_sources}",
            f"Scratch files: {scratch_files}",
            f"Chroma index: {chroma_state}",
            f"Git: {git_state}",
        ]
    )
    return SlashCommandResult("\n".join(lines))


def _handle_model(registry: SlashCommandRegistry, context: SlashCommandContext, args: str) -> SlashCommandResult:
    del registry, args
    api_mode = "responses" if context.use_responses_api else "chat-completions"
    effort = context.reasoning_effort or "none"
    lines = [
        "Model configuration",
        "",
        f"Model: {context.model_name}",
        f"Base URL: {context.chat_base_url}",
        f"API mode: {api_mode}",
        f"Reasoning effort: {effort}",
    ]
    return SlashCommandResult("\n".join(lines))


def _handle_new(registry: SlashCommandRegistry, context: SlashCommandContext, args: str) -> SlashCommandResult:
    del registry, context, args
    return SlashCommandResult(
        reply="Started a fresh conversation thread. Future turns will use a new thread id.",
        action="reset-thread",
    )


def _handle_exit(registry: SlashCommandRegistry, context: SlashCommandContext, args: str) -> SlashCommandResult:
    del registry, context, args
    return SlashCommandResult(reply="Goodbye!", action="exit-app")


def _count_files(directory: Path, *, pattern: str, exclude: Iterable[str] = ()) -> int:
    if not directory.is_dir():
        return 0
    excluded = set(exclude)
    return sum(1 for path in directory.glob(pattern) if path.is_file() and path.name not in excluded)


def _count_all_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.rglob("*") if path.is_file())


def _git_summary(cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return f"unavailable ({exc})"

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "not a git repository"
        return f"unavailable ({detail})"

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return "clean"
    return f"dirty ({len(lines)} changed path{'s' if len(lines) != 1 else ''})"
