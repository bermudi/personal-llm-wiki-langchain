"""Wiki CLI configuration and environment loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

# Required wiki directories
WIKI_DIRS = ("raw", "wiki", "scratch")

# Chat provider (Poe by default — uses your subscription credits)
DEFAULT_CHAT_BASE_URL = "https://api.poe.com/v1"
DEFAULT_CHAT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "low"

# Embedding provider (OpenRouter by default — cheap pay-as-you-go)
DEFAULT_EMBED_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_EMBED_MODEL = "perplexity/pplx-embed-v1-4b"


def require_chat_api_key() -> str:
    """Load chat API key. Defaults to POE_API_KEY."""
    key = os.environ.get("POE_API_KEY")
    if not key:
        print("POE_API_KEY environment variable is required", file=sys.stderr)
        raise SystemExit(1)
    return key


def require_embed_api_key() -> str:
    """Load embedding API key. Defaults to OPENROUTER_API_KEY."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY environment variable is required", file=sys.stderr)
        raise SystemExit(1)
    return key


def get_chat_base_url() -> str:
    return os.environ.get("WIKI_CHAT_BASE_URL", DEFAULT_CHAT_BASE_URL)


def get_model_name() -> str:
    return os.environ.get("WIKI_MODEL", DEFAULT_CHAT_MODEL)


def get_embed_base_url() -> str:
    return os.environ.get("WIKI_EMBED_BASE_URL", DEFAULT_EMBED_BASE_URL)


def get_embedding_model() -> str:
    return os.environ.get("WIKI_EMBED_MODEL", DEFAULT_EMBED_MODEL)


def get_reasoning_effort() -> str | None:
    val = os.environ.get("WIKI_REASONING_EFFORT")
    # Empty string means "no reasoning" (explicit override to disable)
    if val == "" or val == "none":
        return None
    return val if val is not None else DEFAULT_REASONING_EFFORT


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
    kwargs: dict = {
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


def validate_wiki_dir() -> Path:
    """Validate that cwd is a wiki directory. Exit with error if not."""
    cwd = Path.cwd()
    missing = [d for d in WIKI_DIRS if not (cwd / d).is_dir()]
    if missing:
        print(
            f"Not a wiki directory. Missing: {', '.join(missing)}. Run `wiki init` first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return cwd
