# Middleware

## ADDED Requirements

### Requirement: Index Format Linter

The tool SHALL include middleware that validates `wiki/index.md` structure immediately after any `write_file` or `edit_file` call that touches it. Each index entry SHALL have a link, a one-line summary, and sit under a category heading. Duplicate entries for the same page SHALL be rejected. If validation fails, the write SHALL be rejected and the agent SHALL receive an error message describing the format issue.

#### Scenario: Valid index update
- **WHEN** the agent writes a well-formed entry to `wiki/index.md` with a category heading, link, and summary
- **THEN** the write succeeds and the file is updated

#### Scenario: Malformed index entry
- **WHEN** the agent writes an entry missing a link or summary
- **THEN** the middleware rejects the write and returns an error: "Index entry must have a link and one-line summary under a category heading"

#### Scenario: Duplicate entry
- **WHEN** the agent writes an entry for a page that already exists in the index
- **THEN** the middleware rejects the write and returns an error: "Duplicate entry for <page>"

### Requirement: Log Format Linter

The tool SHALL include middleware that validates `wiki/log.md` structure immediately after any `write_file` or `edit_file` call that touches it. Each log entry SHALL follow the format `## [YYYY-MM-DD] <operation> | <description>` and contain at least one bullet point. The log SHALL be append-only — entries SHALL NOT be removed or reordered above the new entry. If validation fails, the write SHALL be rejected.

#### Scenario: Valid log append
- **WHEN** the agent appends a well-formed entry with date, operation type, description, and at least one bullet
- **THEN** the write succeeds

#### Scenario: Missing date format
- **WHEN** the agent writes a log entry without the `[YYYY-MM-DD]` format
- **THEN** the middleware rejects the write and returns an error describing the expected format

#### Scenario: Non-append operation
- **WHEN** the agent writes to `wiki/log.md` in a way that removes or reorders existing entries
- **THEN** the middleware rejects the write and returns an error: "Log is append-only"
