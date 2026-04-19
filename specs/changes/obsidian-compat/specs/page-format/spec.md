# Page Format

## ADDED Requirements

### Requirement: Wikilink Cross-Page References

All cross-page links within wiki pages — including index entries, "Related pages" sections, and inline references to other wiki pages — SHALL use Obsidian wikilink syntax `[[slug|display text]]` where `slug` is the filename stem (without `.md` extension). The agent SHALL NOT use standard markdown link syntax `[text](slug.md)` for references between wiki pages. External URLs and source-file references (e.g., `raw/...`) SHALL continue to use standard markdown links.

#### Scenario: Cross-page link in a concept page
- **WHEN** the agent writes a concept page that references another wiki page
- **THEN** the reference uses `[[minimal-coding-agent-harnesses|Minimal Coding Agent Harnesses]]` syntax

#### Scenario: Index entry linking to a page
- **WHEN** the agent updates `wiki/index.md` with a new entry
- **THEN** the entry link uses `[[slug|Title]]` syntax (e.g., `- [[dylan-patel-on-ai-agents-government-and-asi-race|Dylan Patel on AI Agents, Government Power, and the ASI Race]] — summary text`)

#### Scenario: Source file reference
- **WHEN** the agent references a raw source file path within a page
- **THEN** it uses standard markdown syntax (e.g., `[transcript](../raw/2026-04-13-podcast.md)` or backtick-quoted path)

#### Scenario: Related pages section
- **WHEN** the agent writes a "Related pages" section at the bottom of a wiki page
- **THEN** each entry is a wikilink bullet (e.g., `- [[anthropic-claude-code-controversies|Anthropic, Claude Code, and the Subscription/Source-Leak Controversy]]`)

### Requirement: YAML Frontmatter on Wiki Pages

Every page written to `wiki/` (except `wiki/index.md` and `wiki/log.md`) SHALL include a YAML frontmatter block as the first content in the file. The frontmatter SHALL contain at minimum: `title` (string), `type` (one of `source`, `concept`, `synthesis`, `meta`), `created` (ISO 8601 date string), and `tags` (YAML list of kebab-case strings). The frontmatter SHALL be delimited by `---` on separate lines before and after.

#### Scenario: New concept page frontmatter
- **WHEN** the agent creates `wiki/institutional-trust.md`
- **THEN** the file starts with:
  ```yaml
  ---
  title: Institutional Trust
  type: concept
  created: "2026-04-19"
  tags:
    - institutional-trust
    - social-capital
  ---
  ```

#### Scenario: Source page frontmatter
- **WHEN** the agent creates a source summary page
- **THEN** `type` is `source` and the frontmatter includes a `source` key pointing to the raw file path

#### Scenario: Index and log are exempt
- **WHEN** the agent writes to `wiki/index.md` or `wiki/log.md`
- **THEN** no frontmatter is required (these are structural files with their own format rules)

### Requirement: Inline Tags in Page Content

Wiki pages SHALL include relevant inline `#tag` references within body content. Tags SHALL use kebab-case format (e.g., `#ai-agents`, `#open-source`, `#labor-displacement`). Tags SHALL be placed naturally within prose where they describe the topic being discussed, not appended as a tag cloud at the bottom. The agent SHALL include 3–8 inline tags per page, chosen to represent the page's key topics.

#### Scenario: Tags within a summary section
- **WHEN** the agent writes a summary section about AI agents and software craftsmanship
- **THEN** the prose includes inline tags like `DHH sees #ai-agents as amplifying #software-craft rather than replacing it.`

#### Scenario: No tag cloud at page bottom
- **WHEN** the agent finishes writing a page
- **THEN** inline tags appear only within content prose, not as a standalone list at the end

#### Scenario: Tag format consistency
- **WHEN** the agent writes inline tags
- **THEN** all tags use kebab-case (lowercase, hyphens), never camelCase or snake_case
