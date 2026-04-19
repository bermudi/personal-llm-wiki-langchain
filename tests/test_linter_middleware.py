"""Test that linter middleware validates BEFORE writing to disk.

The key invariant: if validation fails, the file on disk must remain unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import ToolMessage

from wiki.middleware.linter import create_linter_middleware, validate_frontmatter, validate_index, validate_log


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


class TestValidateFrontmatter:
    """Unit tests for the frontmatter validator."""

    def test_valid_frontmatter(self):
        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\ntags:\n  - test\n  - example\n---\n\n# Content\n"
        assert validate_frontmatter(content, "wiki/test.md") is None

    def test_valid_frontmatter_source_type(self):
        content = "---\ntitle: Source Page\ntype: source\ncreated: \"2026-04-19\"\ntags:\n  - podcast\n---\n\n# Content\n"
        assert validate_frontmatter(content, "wiki/source.md") is None

    def test_valid_frontmatter_synthesis_type(self):
        content = "---\ntitle: Synthesis Page\ntype: synthesis\ncreated: \"2026-04-19\"\ntags:\n  - ai\n---\n\n# Content\n"
        assert validate_frontmatter(content, "wiki/synthesis.md") is None

    def test_valid_frontmatter_meta_type(self):
        content = "---\ntitle: Meta Page\ntype: meta\ncreated: \"2026-04-19\"\ntags:\n  - about\n---\n\n# Content\n"
        assert validate_frontmatter(content, "wiki/meta.md") is None

    def test_missing_frontmatter(self):
        content = "# No Frontmatter\n\nJust a regular page.\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "must include YAML frontmatter" in result

    def test_missing_closing_delimiter(self):
        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\ntags:\n  - test\n\n# Content without closing\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "must include YAML frontmatter" in result

    def test_incomplete_frontmatter_missing_tags(self):
        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "missing frontmatter fields" in result
        assert "tags" in result

    def test_incomplete_frontmatter_missing_title(self):
        content = "---\ntype: concept\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "missing frontmatter fields" in result
        assert "title" in result

    def test_invalid_type_value(self):
        content = "---\ntitle: Test Page\ntype: article\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "type must be one of" in result

    def test_empty_title(self):
        content = "---\ntitle: \"\"\ntype: concept\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "title" in result
        assert "non-empty" in result

    def test_tags_not_a_list(self):
        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\ntags: not-a-list\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "tags" in result
        assert "non-empty list" in result

    def test_tags_empty_list(self):
        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\ntags: []\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "tags" in result
        assert "non-empty list" in result

    def test_malformed_yaml(self):
        content = "---\ntitle: Test Page\ntype: concept\n  bad: indentation: here\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n# Content\n"
        # yaml.safe_load may or may not error on this — depends on content.
        # Test with genuinely broken YAML
        content = "---\ntitle: Test Page\ntype: [concept\n---\n\n# Content\n"
        result = validate_frontmatter(content, "wiki/test.md")
        assert result is not None
        assert "malformed YAML" in result


# ---------------------------------------------------------------------------
# Integration tests: middleware blocks the write on validation failure
# ---------------------------------------------------------------------------

def _make_request(tool_name: str, args: dict, tc_id: str = "tc1"):
    """Create a request-like object matching the LangChain middleware contract."""
    return type("Request", (), {"tool_call": {"name": tool_name, "args": args, "id": tc_id}})()


def _call_middleware(middleware, request, handler):
    """Invoke the wrap_tool_call bound method on a middleware instance."""
    return middleware.wrap_tool_call(request, handler)


# Valid frontmatter for reuse in tests
VALID_FRONTMATTER = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n"


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


class TestMiddlewareFrontmatterValidation:
    """Integration tests for frontmatter validation on wiki pages."""

    def test_write_page_with_valid_frontmatter_passes(self, tmp_path):
        """A wiki page with valid frontmatter should pass through to the handler."""
        page_path = tmp_path / "wiki" / "some-topic.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            content = request.tool_call["args"].get("content", "")
            page_path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} chars to wiki/some-topic.md"

        valid_content = VALID_FRONTMATTER + "# Some Topic\n\nContent here.\n"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/some-topic.md",
                "content": valid_content,
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called
        assert page_path.read_text(encoding="utf-8") == valid_content

    def test_write_page_missing_frontmatter_rejected(self, tmp_path):
        """A wiki page without frontmatter must be rejected."""
        page_path = tmp_path / "wiki" / "some-topic.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Should not reach here"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/some-topic.md",
                "content": "# No Frontmatter\n\nJust a regular page.\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content
        assert "must include YAML frontmatter" in result.content

    def test_write_page_incomplete_frontmatter_missing_tags(self, tmp_path):
        """A wiki page with frontmatter missing the tags field must be rejected."""
        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Should not reach here"

        content = "---\ntitle: Test Page\ntype: concept\ncreated: \"2026-04-19\"\n---\n\n# Content\n"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/test.md",
                "content": content,
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content
        assert "missing frontmatter fields" in result.content
        assert "tags" in result.content

    def test_write_page_invalid_type_rejected(self, tmp_path):
        """A wiki page with an invalid type value must be rejected."""
        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Should not reach here"

        content = "---\ntitle: Test Page\ntype: article\ncreated: \"2026-04-19\"\ntags:\n  - test\n---\n\n# Content\n"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/test.md",
                "content": content,
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content
        assert "type must be one of" in result.content

    def test_index_and_log_skip_frontmatter_validation(self, tmp_path):
        """wiki/index.md and wiki/log.md should NOT be validated for frontmatter."""
        # This test writes content without frontmatter to index.md and log.md
        # and expects it to pass (they have their own validators)

        # index.md — no frontmatter, but has a valid index format
        index_path = tmp_path / "wiki" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        index_content = "# Wiki Index\n\n## Topics\n\n- [Foo](wiki/foo.md)\n  Summary\n"

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            content = request.tool_call["args"].get("content", "")
            index_path.write_text(content, encoding="utf-8")
            return f"Wrote content"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "wiki/index.md",
                "content": index_content,
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called  # Should pass through — index has its own validator

        # log.md — no frontmatter, but has a valid log format
        log_path = tmp_path / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_content = "# Wiki Log\n\n## [2026-04-19] ingest | test\n- Added test\n"
        log_path.write_text(log_content, encoding="utf-8")

        handler_called = False

        def handler2(request):
            nonlocal handler_called
            handler_called = True
            new_text = request.tool_call["args"].get("new_text", "")
            old_text = request.tool_call["args"].get("old_text", "")
            content = log_path.read_text(encoding="utf-8").replace(old_text, new_text)
            log_path.write_text(content, encoding="utf-8")
            return "Edited"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware2 = create_linter_middleware()
            request = _make_request("edit_file", {
                "path": "wiki/log.md",
                "old_text": "- Added test\n",
                "new_text": "- Added test\n\n## [2026-04-20] query | more\n- More\n",
            })

            result = _call_middleware(middleware2, request, handler2)

        assert handler_called  # Should pass through — log has its own validator

    def test_edit_preserving_frontmatter_passes(self, tmp_path):
        """An edit_file that preserves frontmatter should succeed."""
        page_path = tmp_path / "wiki" / "some-topic.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)

        original = VALID_FRONTMATTER + "# Some Topic\n\nOld content here.\n"
        page_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            old_text = request.tool_call["args"].get("old_text", "")
            new_text = request.tool_call["args"].get("new_text", "")
            content = page_path.read_text(encoding="utf-8").replace(old_text, new_text)
            page_path.write_text(content, encoding="utf-8")
            return "Edited wiki/some-topic.md"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("edit_file", {
                "path": "wiki/some-topic.md",
                "old_text": "Old content here.",
                "new_text": "New content here.",
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called
        assert "New content here." in page_path.read_text(encoding="utf-8")

    def test_edit_removing_frontmatter_rejected(self, tmp_path):
        """An edit_file that removes frontmatter should be rejected."""
        page_path = tmp_path / "wiki" / "some-topic.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)

        original = VALID_FRONTMATTER + "# Some Topic\n\nContent here.\n"
        page_path.write_text(original, encoding="utf-8")

        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Should not reach here"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            # This edit replaces everything from the frontmatter onward,
            # effectively removing it
            request = _make_request("edit_file", {
                "path": "wiki/some-topic.md",
                "old_text": VALID_FRONTMATTER.strip() + "\n",
                "new_text": "",
            })

            result = _call_middleware(middleware, request, handler)

        assert not handler_called
        assert isinstance(result, ToolMessage)
        assert "VALIDATION ERROR" in result.content

    def test_non_wiki_file_passes_through(self, tmp_path):
        """Files outside wiki/ should pass through without any validation."""
        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Wrote raw file"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "raw/transcript.md",
                "content": "No frontmatter at all\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called

    def test_scratch_file_passes_through(self, tmp_path):
        """Files in scratch/ should pass through without validation."""
        handler_called = False

        def handler(request):
            nonlocal handler_called
            handler_called = True
            return "Wrote scratch file"

        with patch("wiki.middleware.linter.get_wiki_root", return_value=tmp_path):
            middleware = create_linter_middleware()
            request = _make_request("write_file", {
                "path": "scratch/notes.md",
                "content": "Scratch content\n",
            })

            result = _call_middleware(middleware, request, handler)

        assert handler_called