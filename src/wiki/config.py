"""Wiki CLI configuration and environment loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

# Required wiki directories
WIKI_DIRS = ("raw", "wiki", "scratch")

# Provider defaults
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"


def require_api_key() -> str:
    """Load API key from environment. Supports OPENROUTER_API_KEY (preferred) or POE_API_KEY."""
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("POE_API_KEY")
    if not key:
        print(
            "OPENROUTER_API_KEY (or POE_API_KEY) environment variable is required",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return key


def get_base_url() -> str:
    """Get the API base URL. Defaults to OpenRouter."""
    return os.environ.get("WIKI_BASE_URL", DEFAULT_BASE_URL)


def get_model_name() -> str:
    """Get the configured model name."""
    return os.environ.get("WIKI_MODEL", DEFAULT_MODEL)


def get_embedding_model() -> str:
    """Get the configured embedding model name."""
    return os.environ.get("WIKI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def build_model() -> ChatOpenAI:
    """Build a ChatOpenAI model instance configured for the provider."""
    return ChatOpenAI(
        model=get_model_name(),
        base_url=get_base_url(),
        api_key=require_api_key(),
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
