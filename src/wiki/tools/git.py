"""Git tools for the wiki agent."""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import tool


def _git(*args: str) -> str:
    """Run a git command in cwd and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr.strip()}"


@tool
def git_status() -> str:
    """Check the git working tree status.

    Returns the list of modified, added, or deleted files. Use this before
    modifying wiki files to detect human edits that must be preserved.
    """
    output = _git("status", "--porcelain")
    if not output:
        return "Working tree clean. No uncommitted changes."
    return output


@tool
def git_commit(message: str) -> str:
    """Commit staged changes with the given message.

    Write/edit tools stage files as they go — this just seals the index.
    The message should follow the pattern: <operation>: <description>
    For example: "ingest: podcast-guest-topic" or "query: comparison of X and Y"

    Args:
        message: Commit message following the operation pattern.
    """
    # Check if there's anything staged to commit
    diff = _git("diff", "--cached", "--name-only")
    if not diff:
        return "Nothing to commit. No files staged."

    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    if result.returncode == 0:
        return f"Committed: {message}"
    return f"Error: {result.stderr.strip()}"


@tool
def git_log(n: int = 10) -> str:
    """View recent git commit history.

    Use this to see what operations have been performed, check commit messages,
    or understand the wiki's change history.

    Args:
        n: Number of recent commits to show. Defaults to 10.
    """
    return _git("log", f"-{n}", "--oneline")
