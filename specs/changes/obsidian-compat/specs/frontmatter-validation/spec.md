# Frontmatter Validation

## ADDED Requirements

### Requirement: Frontmatter Validation Middleware

The linter middleware SHALL validate YAML frontmatter on every `write_file` or `edit_file` call targeting a `wiki/*.md` file (excluding `wiki/index.md` and `wiki/log.md`). The middleware SHALL reject writes where the proposed content is missing frontmatter or has invalid frontmatter. Valid frontmatter SHALL contain at minimum: `title` (non-empty string), `type` (one of `source`, `concept`, `synthesis`, `meta`), `created` (ISO 8601 date), and `tags` (non-empty list). The middleware SHALL parse the YAML block between the opening `---` and closing `---` delimiters.

#### Scenario: Page with valid frontmatter
- **WHEN** the agent writes `wiki/some-topic.md` with complete YAML frontmatter containing title, type, created, and tags
- **THEN** the write succeeds

#### Scenario: Page missing frontmatter
- **WHEN** the agent writes `wiki/some-topic.md` without any `---`-delimited frontmatter block
- **THEN** the middleware rejects the write and returns an error: "VALIDATION ERROR: wiki/some-topic.md must include YAML frontmatter with title, type, created, and tags"

#### Scenario: Page with incomplete frontmatter
- **WHEN** the agent writes `wiki/some-topic.md` with frontmatter that is missing the `tags` field
- **THEN** the middleware rejects the write and returns an error naming the missing field(s)

#### Scenario: Page with invalid type value
- **WHEN** the agent writes `wiki/some-topic.md` with `type: article`
- **THEN** the middleware rejects the write with error: "VALIDATION ERROR: type must be one of: source, concept, synthesis, meta"

#### Scenario: Index and log are not validated for frontmatter
- **WHEN** the agent writes to `wiki/index.md` or `wiki/log.md`
- **THEN** no frontmatter validation runs (existing index/log linters still apply)

#### Scenario: Edit preserves existing frontmatter
- **WHEN** the agent uses `edit_file` to change body content on a page that already has valid frontmatter
- **THEN** the edit succeeds because the frontmatter remains intact after the edit
