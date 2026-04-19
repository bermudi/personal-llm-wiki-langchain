## Architecture

This change modifies two surfaces: the agent's prompt (controls output format) and the linter middleware (enforces format on write). No new tools, no new files, no data model changes.

```
agent.py (SYSTEM_PROMPT)
  │  tells the agent to use wikilinks, frontmatter, inline tags
  ▼
tools/filesystem.py (write_file, edit_file)
  │  unchanged — already passes content through middleware
  ▼
middleware/linter.py
  │  adds frontmatter validation alongside existing index/log linters
  ▼
wiki/*.md (output)
     now contains frontmatter + wikilinks + inline tags
```

The flow is: agent decides to write → middleware intercepts → validates frontmatter on wiki pages → passes or rejects → file lands on disk. This is the same intercept pattern already used for index.md and log.md.

## Decisions

### Wikilinks over markdown links for cross-page refs

**Chosen:** `[[slug|display text]]` syntax for all wiki-to-wiki links.

**Why:** This is the Obsidian-native format. It activates backlinks, graph view, and click-through navigation without any plugin. Markdown links `[text](file.md)` still render in Obsidian, but they don't contribute to the backlink graph.

**Constraint:** Only applies to wiki-internal links. External URLs and `raw/` file references keep markdown link syntax since they're not wiki pages.

**Trade-off:** Wikilinks don't render outside Obsidian (e.g., on GitHub). Accepted because the primary consumer is Obsidian, and GitHub rendering is secondary.

### Frontmatter fields: title, type, created, tags

**Chosen:** Four mandatory fields. `source` field optional (only on source-type pages).

**Why:** `title` and `type` enable Obsidian property search and Dataview filtering. `created` enables temporal queries. `tags` provides the tag pane. `source` is useful metadata for source pages but meaningless for concepts/syntheses.

**Constraint:** `type` is an enum (`source | concept | synthesis | meta`) matching the index categories. This keeps the agent honest about classification.

### Inline tags within prose, not tag clouds

**Chosen:** Tags embedded naturally in content (e.g., `the #ai-agents space`). No tag list at the bottom.

**Why:** Obsidian indexes inline tags regardless of position. Embedding them in prose keeps the page readable as a document while still being discoverable via the tag pane.

**Constraint:** 3–8 tags per page to avoid both under-tagging (invisible) and over-tagging (noise). Kept as a prompt guideline, not enforced by the linter — the linter validates frontmatter tags exist, not inline tags.

### No migration for existing pages

**Chosen:** Existing pages stay as-is. New pages and edits use the new format.

**Why:** Obsidian handles mixed link formats gracefully. The backlink graph will be partial until pages get re-edited, but that's acceptable. A bulk migration would be risky (could break content) and low-value.

### Linter validates frontmatter, not inline tags

**Chosen:** The middleware enforces frontmatter structure but does not validate inline tag presence or format.

**Why:** Inline tags are a quality signal, not a structural requirement. Validating them in middleware would be fragile (regex on prose) and would create false negatives. The prompt guides tag usage; the linter guards the contract.

## File Changes

### `src/wiki/agent.py`
- **What:** Update `SYSTEM_PROMPT` with three new format rules:
  1. Wikilink syntax rule with examples for index entries, related-pages sections, and inline refs
  2. Frontmatter structure rule with required fields and example block
  3. Inline tag rule with format (kebab-case) and placement guidance
- **Why:** The system prompt is the single control point for agent output format. All three requirements trace to the page-format spec.
- **Spec references:** Wikilink Cross-Page References, YAML Frontmatter on Wiki Pages, Inline Tags in Page Content

### `src/wiki/middleware/linter.py`
- **What:** Add a `validate_frontmatter(content, path)` function that:
  - Parses the YAML block between opening `---` and closing `---`
  - Checks for required fields: `title`, `type`, `created`, `tags`
  - Validates `type` is in the allowed enum
  - Validates `tags` is a non-empty list
  - Returns an error string or `None`
- **What:** Extend `create_linter_middleware()` to call `validate_frontmatter` for all `wiki/*.md` writes except `wiki/index.md` and `wiki/log.md`
- **Why:** Prevents the agent from writing pages without frontmatter. Enforces the contract from the frontmatter-validation spec.
- **Spec reference:** Frontmatter Validation Middleware
- **Impact on callers:** None — middleware is transparent to the agent. Invalid writes return `ToolMessage` errors the same way existing index/log validation does.

### `tests/test_linter_middleware.py`
- **What:** Add test cases for frontmatter validation:
  - Valid frontmatter passes
  - Missing frontmatter rejected
  - Incomplete frontmatter (missing tags) rejected
  - Invalid type value rejected
  - index.md and log.md skip frontmatter validation
  - Edit that preserves frontmatter passes
- **Why:** Existing tests cover index/log linting. New validation needs the same coverage.
- **Spec reference:** All Frontmatter Validation Middleware scenarios
