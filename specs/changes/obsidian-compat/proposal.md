## Motivation

The wiki generates standard markdown pages that render fine in any editor, but they are invisible to Obsidian's core features — graph view, backlink pane, tag pane, property search, and Dataview queries. Every cross-page link uses `[text](slug.md)` syntax, pages have no frontmatter, and there are no inline tags. The wiki is a flat file store that happens to live in a vault folder; it should be a first-class Obsidian knowledge graph.

Making the wiki Obsidian-compatible turns the static file tree into an explorable graph with zero additional tooling.

## Scope

Three capabilities, all targeting the agent's output format (what it writes to `wiki/*.md`):

1. **Wikilinks for cross-page references.** All links between wiki pages — including index entries, "Related pages" sections, and inline references — SHALL use `[[slug|display text]]` syntax instead of `[text](slug.md)`. The slug is the filename stem (e.g., `dylan-patel-on-ai-agents-government-and-asi-race`). This activates Obsidian's backlink pane and graph view automatically.

2. **YAML frontmatter on every wiki page.** Every page written to `wiki/` SHALL include a frontmatter block with at minimum `title`, `type` (one of `source`, `concept`, `synthesis`, `meta`), `created` (ISO date), and `tags` (list). This unlocks Obsidian's property search, tag pane, and Dataview queries.

3. **Inline tags within page content.** Pages SHALL include relevant inline `#tag` references within body content (e.g., `#ai-agents`, `#open-source`). These are separate from the frontmatter `tags` list and provide Obsidian's tag-pane discoverability at the content level.

### What changes

- `src/wiki/agent.py` — `SYSTEM_PROMPT` updated with format rules for wikilinks, frontmatter, and inline tags
- `src/wiki/middleware/linter.py` — New validation for frontmatter presence and structure on all `wiki/*.md` writes
- Existing wiki pages do NOT need migration — Obsidian renders both `[text](file.md)` and `[[file|text]]`, so old pages continue to work. The agent will use the new format going forward.

### Affected capabilities

- Page creation (ingest, consolidate)
- Page editing (query-driven updates)
- Index maintenance (`wiki/index.md` link format)
- Linter middleware (new frontmatter validation)

## Non-Goals

- **Migration script for existing pages.** Old markdown-link pages still render in Obsidian. Re-ingesting sources or a bulk migration is a separate concern.
- **Obsidian plugin or theme.** This is purely about file format — no `.obsidian/` config, custom CSS, or plugin development.
- **Folder structure changes.** Pages stay flat in `wiki/`. No subfolder hierarchy or MOC (Map of Content) changes.
- **Template system.** The agent prompt already controls page structure. No need for a separate template engine.
- **Bi-directional sync.** Files edited directly in Obsidian are not tracked or reconciled (that's the git workflow's job).
- **Graph view customization.** We emit the right links; how Obsidian renders them is out of scope.
