"""Index and log format validation middleware."""

from __future__ import annotations

import re
from pathlib import Path

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

from wiki.config import get_wiki_root


def validate_index(content: str) -> str | None:
    """Validate wiki/index.md format. Returns error message or None if valid."""
    lines = content.split("\n")

    # Must have a top-level heading
    if not any(line.startswith("# ") for line in lines):
        return "Index must have a top-level heading (e.g., '# Wiki Index')"

    # Track entries to detect duplicates
    seen_entries: set[str] = set()
    in_entry = False
    current_link: str | None = None

    for line in lines:
        stripped = line.strip()

        # Category heading
        if stripped.startswith("## "):
            in_entry = False
            current_link = None
            continue

        # Detect markdown links — these are index entries
        link_match = re.match(r"-?\s*\[([^\]]+)\]\(([^)]+)\)", stripped)
        if link_match:
            link_path = link_match.group(2)
            if link_path in seen_entries:
                return f"Duplicate entry for {link_path}"
            seen_entries.add(link_path)
            current_link = link_path
            in_entry = True

            # Entry must have a link and some summary text on same or next line
            # (the link itself counts as having a link)
            continue

        # Non-empty, non-heading line under an entry could be summary text
        if in_entry and stripped and not stripped.startswith("#") and not stripped.startswith("##"):
            # This is summary text for the current entry — good
            continue

    return None


def validate_log(content: str, original_content: str) -> str | None:
    """Validate wiki/log.md format. Returns error message or None if valid.

    The log is append-only — existing entries must not be removed or reordered.
    """
    lines = content.split("\n")

    # Must have a top-level heading
    if not any(line.startswith("# ") for line in lines):
        return "Log must have a top-level heading (e.g., '# Wiki Log')"

    # Check append-only: original content must be a prefix of new content
    if original_content and not content.startswith(original_content.rstrip() + "\n") and content != original_content:
        # Allow the new content to be identical or have the original as a prefix
        original_stripped = original_content.rstrip()
        content_stripped = content.rstrip()
        if not content_stripped.startswith(original_stripped):
            return "Log is append-only. Existing entries must not be removed or reordered."

    # Find all date entries: ## [YYYY-MM-DD] operation | description
    entry_pattern = re.compile(r"^##\s+\[(\d{4}-\d{2}-\d{2})\]\s+.+\|")
    entries = [(i, line) for i, line in enumerate(lines) if entry_pattern.match(line.strip())]

    if not entries:
        return None  # Empty log (just header) is valid

    # Each entry must have at least one bullet point
    for idx, entry_line in entries:
        # Look for at least one bullet in the lines following this entry
        has_bullet = False
        for j in range(idx + 1, len(lines)):
            next_line = lines[j].strip()
            if next_line.startswith("## "):
                break  # Hit next entry
            if next_line.startswith("- ") or next_line.startswith("* "):
                has_bullet = True
                break
        if not has_bullet:
            return f"Log entry '{entry_line.strip()}' must have at least one bullet point"

    return None


def create_linter_middleware():
    """Create middleware that validates index.md and log.md on write/edit."""

    @wrap_tool_call
    def linter_middleware(request, handler):
        tool_name = request.tool_call["name"]
        args = request.tool_call["args"]

        # Only intercept write_file and edit_file
        if tool_name not in ("write_file", "edit_file"):
            return handler(request)

        path = args.get("path", "")
        is_index = path.rstrip("/") == "wiki/index.md"
        is_log = path.rstrip("/") == "wiki/log.md"

        if not is_index and not is_log:
            return handler(request)

        # For edit_file, we need to read the current content first (for append-only check on log)
        original_content = ""
        if tool_name == "edit_file" and is_log:
            try:
                original_content = (get_wiki_root() / path).read_text(encoding="utf-8")
            except FileNotFoundError:
                pass

        # Execute the tool call — handler returns a ToolMessage (per wrap_tool_call contract)
        result = handler(request)

        # If the tool already returned an error, pass it through
        if isinstance(result, ToolMessage) and isinstance(result.content, str) and result.content.startswith("Error:"):
            return result

        # Read the new content to validate
        try:
            new_content = (get_wiki_root() / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return result

        # Validate — return a ToolMessage with the error so the agent can self-correct
        tc_id = request.tool_call.get("id")

        if is_index:
            error = validate_index(new_content)
            if error:
                return ToolMessage(
                    content=f"VALIDATION ERROR: {error}",
                    tool_call_id=tc_id or "",
                    name=tool_name,
                )

        if is_log:
            error = validate_log(new_content, original_content)
            if error:
                return ToolMessage(
                    content=f"VALIDATION ERROR: {error}",
                    tool_call_id=tc_id or "",
                    name=tool_name,
                )

        return result

    return linter_middleware
