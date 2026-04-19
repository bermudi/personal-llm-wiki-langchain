## Phase 1: Frontmatter Validation

Add the linter guard that enforces frontmatter on all wiki pages. This is the structural enforcement layer — ship it first so the agent can't accidentally write un-frontmatter'd pages even before the prompt is updated.

- [ ] Add `validate_frontmatter(content: str, path: str) -> str | None` to `src/wiki/middleware/linter.py` that parses YAML between `---` delimiters, checks for `title`, `type` (enum: source/concept/synthesis/meta), `created` (ISO date), and `tags` (non-empty list). Returns error message or `None`. — *spec: Frontmatter Validation Middleware*
- [ ] Extend `create_linter_middleware()` to call `validate_frontmatter` for `write_file`/`edit_file` calls on `wiki/*.md` files, excluding `wiki/index.md` and `wiki/log.md`. Intercept before the handler, same pattern as existing index/log validation. — *spec: Frontmatter Validation Middleware*
- [ ] Add `import yaml` to linter.py and add `pyyaml` to project dependencies in `pyproject.toml`. — *build dependency*
- [ ] Add tests to `tests/test_linter_middleware.py`: valid frontmatter passes, missing frontmatter rejected, incomplete fields rejected, invalid type rejected, index/log exempt, edit preserving frontmatter passes. — *spec: all Frontmatter Validation Middleware scenarios*

## Phase 2: System Prompt Update

Update the agent prompt to produce wikilinks, frontmatter, and inline tags. This is the behavioral layer — tells the agent what format to use.

- [ ] Add wikilink format rule to `SYSTEM_PROMPT` in `src/wiki/agent.py`: cross-page links use `[[slug|display]]`, with examples for index entries, related-pages sections, and inline refs. External URLs and raw-source paths keep markdown link syntax. — *spec: Wikilink Cross-Page References*
- [ ] Add frontmatter format rule to `SYSTEM_PROMPT`: every wiki page (except index.md, log.md) starts with `---`-delimited YAML containing `title`, `type`, `created`, `tags`. Include a concrete example block. — *spec: YAML Frontmatter on Wiki Pages*
- [ ] Add inline tag rule to `SYSTEM_PROMPT`: embed 3–8 `#kebab-case` tags naturally within prose. No tag clouds at the bottom. — *spec: Inline Tags in Page Content*

## Phase 3: Verify End-to-End

Manual verification that the full pipeline produces Obsidian-compatible output.

- [ ] Run `uv run wiki ingest` against a test source in `test-wiki/raw/` and confirm the generated page has valid frontmatter, wikilinks in related-pages and index, and inline tags in body content.
- [ ] Open `test-wiki/wiki/` as an Obsidian vault (or verify Obsidian-compatible structure) and confirm graph view shows links, backlinks panel populates, tag pane shows inline tags, and property search finds frontmatter fields.
- [ ] Run the full test suite (`uv run pytest`) and confirm all tests pass including new linter tests.
