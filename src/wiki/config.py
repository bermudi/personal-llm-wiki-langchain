"""Wiki CLI configuration and environment loading."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


# ── .wiki/.env (secrets) ───────────────────────────────────────────────

_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    """Load ``.wiki/.env`` into ``os.environ`` if it exists.

    Idempotent — only loads once per process.
    Values from the file **clobber** any existing env vars so that
    ``.wiki/.env`` is the canonical source for secrets.  This lets users run
    multiple wikis with different tokens from the same shell.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    env_path = get_wiki_root() / ".wiki" / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


# ── .wiki/config.toml (non-secret config) ───────────────────────────────

_CONFIG: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """Load ``.wiki/config.toml`` if it exists. Cached per process."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    config_path = get_wiki_root() / ".wiki" / "config.toml"
    if config_path.is_file():
        with open(config_path, "rb") as f:
            _CONFIG = tomllib.load(f)
    else:
        _CONFIG = {}
    return _CONFIG


def _config_value(section: str, key: str, default: str | None = None) -> str | None:
    """Read a value from config.toml. Returns ``default`` if not set."""
    cfg = _load_config()
    val = cfg.get(section, {}).get(key, default)
    return val if isinstance(val, str) else default


# Required wiki directories
WIKI_DIRS = ("raw", "wiki", "scratch")

# Fallback defaults (used when neither config.toml nor env vars set a value)
DEFAULT_CHAT_BASE_URL = "https://api.poe.com/v1"
DEFAULT_CHAT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "low"

DEFAULT_EMBED_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_EMBED_MODEL = "perplexity/pplx-embed-v1-4b"


# ── Wiki root (cached once per process) ──────────────────────────────────

_wiki_root: Path | None = None


def set_wiki_root(path: Path) -> None:
    """Set the wiki root directory explicitly.

    Called by :func:`validate_wiki_dir` and in tests.
    """
    global _wiki_root
    _wiki_root = path


def get_wiki_root() -> Path:
    """Return the wiki root directory.

    Returns the cached value if :func:`set_wiki_root` or
    :func:`validate_wiki_dir` has been called; otherwise falls back to
    ``Path.cwd()``.
    """
    if _wiki_root is not None:
        return _wiki_root
    return Path.cwd()


def require_chat_api_key() -> str:
    """Load chat API key. Resolution: ``.wiki/.env`` → ``POE_API_KEY`` env var → error."""
    _load_dotenv_once()
    key = os.environ.get("POE_API_KEY")
    if not key:
        print("POE_API_KEY not found. Set it in .wiki/.env or as an environment variable.", file=sys.stderr)
        raise SystemExit(1)
    return key


def require_embed_api_key() -> str:
    """Load embedding API key. Resolution: ``.wiki/.env`` → ``OPENROUTER_API_KEY`` env var → error."""
    _load_dotenv_once()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not found. Set it in .wiki/.env or as an environment variable.", file=sys.stderr)
        raise SystemExit(1)
    return key


def require_telegram_bot_token() -> str:
    """Load Telegram bot token for polling mode.

    Resolution order: ``.wiki/.env`` → ``TELEGRAM_BOT_TOKEN`` env var → error.
    """
    _load_dotenv_once()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print(
            "TELEGRAM_BOT_TOKEN not found. Set it in .wiki/.env or as an environment variable.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return token


def get_chat_base_url() -> str:
    return os.environ.get("WIKI_CHAT_BASE_URL", _config_value("chat", "base_url", DEFAULT_CHAT_BASE_URL) or DEFAULT_CHAT_BASE_URL)


def get_model_name() -> str:
    return os.environ.get("WIKI_MODEL", _config_value("chat", "model", DEFAULT_CHAT_MODEL) or DEFAULT_CHAT_MODEL)


def get_embed_base_url() -> str:
    return os.environ.get("WIKI_EMBED_BASE_URL", _config_value("embed", "base_url", DEFAULT_EMBED_BASE_URL) or DEFAULT_EMBED_BASE_URL)


def get_embedding_model() -> str:
    return os.environ.get("WIKI_EMBED_MODEL", _config_value("embed", "model", DEFAULT_EMBED_MODEL) or DEFAULT_EMBED_MODEL)


def get_reasoning_effort() -> str | None:
    val = os.environ.get("WIKI_REASONING_EFFORT")
    if val is not None:
        # Empty string means "no reasoning" (explicit override to disable)
        return None if val in ("", "none") else val
    from_toml = _config_value("chat", "reasoning_effort", DEFAULT_REASONING_EFFORT)
    return None if from_toml in ("", "none") else from_toml


def get_use_responses_api() -> bool:
    """Whether to use the Responses API instead of Chat Completions.

    Defaults to False because langchain-openai's Responses API mode has a bug
    in multi-turn tool conversations (duplicates function_call items in the
    input array).  The raw OpenAI SDK against Poe works fine — the bug is in
    how langchain-openai reconstructs the input array from AIMessage state.

    Set WIKI_USE_RESPONSES_API=true to opt in (e.g. for reasoning tokens
    with a provider that fixes the langchain-openai issue or isn't Poe).
    """
    val = os.environ.get("WIKI_USE_RESPONSES_API", "").lower()
    return val in ("1", "true", "yes")


def build_model() -> ChatOpenAI:
    """Build a ChatOpenAI instance for the chat provider.

    Uses Chat Completions (POST /v1/chat/completions) by default — the most
    reliable path through Poe with zero platform gaps (system messages,
    tools, multi-turn, streaming all confirmed).

    Reasoning effort is passed through on both paths:
      - Chat Completions → reasoning_effort param (official OpenAI field)
      - Responses API   → reasoning.effort + summary (structured)
    Note: Chat Completions does not stream reasoning tokens back, but the
    model still uses the effort level internally.
    """
    use_responses = get_use_responses_api()
    kwargs: dict[str, Any] = {
        "model": get_model_name(),
        "base_url": get_chat_base_url(),
        "api_key": require_chat_api_key(),
        "use_responses_api": use_responses,
    }
    effort = get_reasoning_effort()
    if effort:
        if use_responses:
            kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
        else:
            kwargs["reasoning_effort"] = effort
    return ChatOpenAI(**kwargs)


def build_embeddings() -> OpenAIEmbeddings:
    """Build an OpenAI-compatible embeddings client for chunk + wiki indexing."""
    return OpenAIEmbeddings(
        model=get_embedding_model(),
        base_url=get_embed_base_url(),
        api_key=require_embed_api_key(),
    )


def validate_wiki_dir() -> Path:
    """Validate that cwd is a wiki directory. Exit with error if not.

    Caches the validated root so subsequent :func:`get_wiki_root` calls
    return it without re-checking.
    """
    cwd = Path.cwd()
    missing = [d for d in WIKI_DIRS if not (cwd / d).is_dir()]
    if missing:
        print(
            f"Not a wiki directory. Missing: {', '.join(missing)}. Run `wiki init` first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    set_wiki_root(cwd)
    return cwd
