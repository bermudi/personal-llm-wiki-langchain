"""Wiki CLI configuration and environment loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

# Required wiki directories
WIKI_DIRS = ("raw", "wiki", "scratch")


def require_api_key() -> str:
    """Load POE_API_KEY from environment. Exit with error if missing."""
    key = os.environ.get("POE_API_KEY")
    if not key:
        print("POE_API_KEY environment variable is required", file=sys.stderr)
        raise SystemExit(1)
    return key


def get_model_name() -> str:
    """Get the configured model name. Defaults to gpt-5.4."""
    return os.environ.get("WIKI_MODEL", "gpt-5.4")


def build_model() -> ChatOpenAI:
    """Build a ChatOpenAI model instance configured for Poe API."""
    return ChatOpenAI(
        model=get_model_name(),
        base_url="https://api.poe.com/v1",
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
