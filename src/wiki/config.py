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
DEFAULT_CHAT_MODEL = "gpt-4.1-mini"

# Embedding provider (OpenRouter by default — cheap pay-as-you-go)
DEFAULT_EMBED_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_EMBED_MODEL = "openai/text-embedding-3-small"


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


def build_model() -> ChatOpenAI:
    """Build a ChatOpenAI instance for the chat provider."""
    return ChatOpenAI(
        model=get_model_name(),
        base_url=get_chat_base_url(),
        api_key=require_chat_api_key(),
    )


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
