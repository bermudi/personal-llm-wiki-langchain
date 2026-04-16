"""Test that linter middleware validates BEFORE writing to disk.

The key invariant: if validation fails, the file on disk must remain unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import ToolMessage

from wiki.middleware.linter import create_linter_middleware, validate_index, validate_log


# ---------------------------------------------------------------------------
# Unit tests for the pure validators
# ---------------------------------------------------------------------------

class TestValidateIndex:
    def test_valid_index(self):
        content = "# Wiki Index\n\n## Topics\n\n- [Foo](wiki/foo.md)\n  Summary of foo\n"
        assert validate_index(content) is None

    def test_missing_heading(self):
        content = "## Topics\n\n- [Foo](wiki/foo.md)\n"
        assert "top-level heading" in validate_index(content)

    def test_duplicate_entry(self):
        content = "# Wiki Index\n\n## Topics\n\n- [Foo](wiki/foo.md)\n- [Foo](wiki/foo.md)\n"
        assert "Duplicate" in validate_index(content)


class TestValidateLog:
    def test_valid_log(self):
        content = "# Wiki Log\n\n## [2025-01-01] ingest | added foo\n- Added foo\n"
        assert validate_log(content, "") is None

    def test_missing_heading(self):
        content = "## [2025-01-01] ingest | added foo\n- Added foo\n"
        assert "top-level heading" in validate_log(content, "")

    def test_append_only_violation(self):
        original = "# Wiki Log\n\n## [2025-01-01] ingest | added foo\n- Added foo\n"
        modified = "# Wiki Log\n\n## [2025-01-02] ingest | added bar\n- Added bar\n"
        assert "append-only" in validate_log(modified, original)


# ---------------------------------------------------------------------------
# Integration tests: middleware blocks the write on validation failure
# ---------------------------------------------------------------------------

def _make_request(tool_name: str, args: dict, tc_id: str = "tc1"):
    """Create a request-like object matching the LangChain middleware contract."""
    return type("Request", (), {"tool_call": {"name": tool_name, "args": args, "id": tc_id}})()


def _call_middleware(middleware, request, handler):
    """Invoke the wrap_tool_call bound method on a middleware instance."""
    return middleware.wrap_tool_call(request, handler)


class TestMiddlewareBlocksWriteOnValidationError:
    """The file must NEVER be written when validation fails."""

    def test_write_invalid_index_never_reaches_disk(self, tmp_path):
        """If write_file attempts to write an index with no heading, the handler
        must NOT be called — the file on disk must stay clean."""
        index_path = tmp_path / "wiki" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        # Pre-existing valid index
        index_path.write_text("# Wiki Index\n\n## Topics\n\n- [A](wiki/a.md)\n", encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            # If the handler runs, it would write invalid content
            content = request.tool_call["args"].get("content", "")
            index_path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} chars to wiki/index.md"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/index.md",
                "content": "## No top heading\n\n- [Foo](wiki/foo.md)\n",
            })

            result = _call_middleware(middleware, request, handler)

        # Handler must NOT have been called
        assert not handler_called, "Handler should not be called when validation fails"

        # Result must be a ToolMessage with validation error
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content

        # File on disk must still be the original valid content
        assert "# Wiki Index" in index_path.read_text(encoding="utf-8")

    def test_write_invalid_log_never_reaches_disk(self, tmp_path):
        """If write_file attempts to write an invalid log, the handler must NOT run."""
        log_path = tmp_path / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        original = "# Wiki Log\n\n## [2025-01-01] ingest | foo\n- foo\n"
        log_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return f"Wrote stuff"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            # Log with no top-level heading
            request = _make_request("write_file", {
                "path": "wiki/log.md",
                "content": "## [2025-01-01] ingest | foo\n- foo\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content

        # Original log untouched
        assert log_path.read_text(encoding="utf-8") == original

    def test_edit_invalid_log_never_reaches_disk(self, tmp_path):
        """edit_file that violates append-only must not modify the file."""
        log_path = tmp_path / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        original = "# Wiki Log\n\n## [2025-01-01] ingest | foo\n- foo\n"
        log_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Edited wiki/log.md"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            # Replace text that would break append-only
            request = _make_request("edit_file", {
                "path": "wiki/log.md",
                "old_text": "## [2025-01-01] ingest | foo",
                "new_text": "## [2025-01-02] ingest | bar",
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content

        # Original log untouched
        assert log_path.read_text(encoding="utf-8") == original

    def test_valid_write_passes_through(self, tmp_path):
        """A valid write must pass through to the handler and succeed."""
        index_path = tmp_path / "wiki" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            content = request.tool_call["args"].get("content", "")
            index_path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} chars to wiki/index.md"

        valid_content = "# Wiki Index\n\n## Topics\n\n- [Foo](wiki/foo.md)\n  Summary\n"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/index.md",
                "content": valid_content,
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called
        assert isinstance(result, str) or (isinstance(result, ToolMessage) and "VALIDATION ERROR" not in result.content)
        assert index_path.read_text(encoding="utf-8") == valid_content

    def test_valid_edit_passes_through(self, tmp_path):
        """A valid edit (appending to log) must pass through."""
        log_path = tmp_path / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        original = "# Wiki Log\n\n## [2025-01-01] ingest | foo\n- foo\n"
        log_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            new_text = request.tool_call["args"].get("new_text", "")
            old_text = request.tool_call["args"].get("old_text", "")
            content = log_path.read_text(encoding="utf-8").replace(old_text, new_text)
            log_path.write_text(content, encoding="utf-8")
            return "Edited wiki/log.md"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            # Append a new entry — valid
            request = _make_request("edit_file", {
                "path": "wiki/log.md",
                "old_text": "- foo\n",
                "new_text": "- foo\n\n## [2025-01-02] query | bar\n- bar\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called

    def test_non_watched_file_passes_through(self, tmp_path):
        """Files that are not index.md or log.md must pass through without validation."""
        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Wrote other.md"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/other.md",
                "content": "No heading at all\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called

    def test_edit_file_text_not_found_returns_error(self, tmp_path):
        """edit_file where old_text is not found must return a validation error
        without calling the handler."""
        log_path = tmp_path / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        original = "# Wiki Log\n\n## [2025-01-01] ingest | foo\n- foo\n"
        log_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Should not reach here"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("edit_file", {
                "path": "wiki/log.md",
                "old_text": "nonexistent text",
                "new_text": "replacement",
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "not found" in result.content.lower()
        # Original intact
        assert log_path.read_text(encoding="utf-8") == original