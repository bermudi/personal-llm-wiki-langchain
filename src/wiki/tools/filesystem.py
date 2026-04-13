"""Filesystem tools for the wiki agent."""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import tool


def _resolve(path: str) -> Path:
    """Resolve a path relative to cwd."""
    return Path.cwd() / path


@tool
def read_file(path: str) -> str:
    """Read the full contents of a file.

    Use this to read raw sources, wiki pages, or any file in the project.

    Args:
        path: File path relative to the wiki root (cwd).
    """
    resolved = _resolve(path)
    if not resolved.exists():
        return f"Error: File not found: {path}"
    if not resolved.is_file():
        return f"Error: Not a file: {path}"
    return resolved.read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it doesn't exist.

    Use this to create wiki pages, update the index, or write any file.

    Args:
        path: File path relative to the wiki root (cwd).
        content: Full file content to write.
    """
    resolved = _resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Make a targeted edit to a file by replacing exact text.

    Use this for small changes to existing files — updating an index entry,
    fixing a section, or appending to the log.

    Args:
        path: File path relative to the wiki root (cwd).
        old_text: Exact text to find and replace.
        new_text: Replacement text.
    """
    resolved = _resolve(path)
    if not resolved.exists():
        return f"Error: File not found: {path}"

    content = resolved.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        return f"Error: Text not found in {path}"
    if count > 1:
        return f"Error: Found {count} matches in {path}. Provide more context for a unique match."

    new_content = content.replace(old_text, new_text)
    resolved.write_text(new_content, encoding="utf-8")
    return f"Edited {path}: replaced {len(old_text)} chars with {len(new_text)} chars"


@tool
def list_files(directory: str = ".") -> str:
    """List files and directories in a directory.

    Use this to explore the wiki structure, find pages, or check what exists.

    Args:
        directory: Directory path relative to the wiki root (cwd). Defaults to root.
    """
    resolved = _resolve(directory)
    if not resolved.exists():
        return f"Error: Directory not found: {directory}"
    if not resolved.is_dir():
        return f"Error: Not a directory: {directory}"

    entries = sorted(resolved.iterdir())
    lines = []
    for entry in entries:
        name = entry.name
        if entry.is_dir():
            lines.append(f"  {name}/")
        else:
            lines.append(f"  {name}")
    return f"{directory}:\n" + "\n".join(lines)


@tool
def search_files(pattern: str) -> str:
    """Search for a text pattern across all wiki files using grep.

    Use this to find pages mentioning a topic, locate entries, or discover content.

    Args:
        pattern: Text pattern to search for (regex supported).
    """
    try:
        result = subprocess.run(
            ["rg", "--no-heading", "-n", "--max-count", "50", pattern, "."],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            return output if output else "No matches found."
        return "No matches found."
    except FileNotFoundError:
        # Fallback to Python re if rg not available
        import re

        matches = []
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex: {e}"

        for md_file in Path.cwd().rglob("*.md"):
            if ".git" in md_file.parts or ".chroma" in md_file.parts:
                continue
            try:
                for i, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
                    if regex.search(line):
                        rel = md_file.relative_to(Path.cwd())
                        matches.append(f"{rel}:{i}:{line.strip()}")
                        if len(matches) >= 50:
                            break
            except (OSError, UnicodeDecodeError):
                continue
            if len(matches) >= 50:
                break

        return "\n".join(matches) if matches else "No matches found."
