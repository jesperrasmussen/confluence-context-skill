# Confluence Context Skill

Extracts and structures project context from Confluence documentation to build agent-ready briefs.

## Purpose

Fetches documentation from Confluence, extracts business context (stakeholders, constraints, business value, processes), structures it as JSON, and generates summaries for agent briefings.

## Features

- Manual skill invocation to fetch and update context
- Structured JSON output for programmatic access
- Human-readable markdown summaries
- Per-project Confluence configuration
- Interactive prompting for fields that can't be auto-extracted
- Auto-load support via hooks (when integrated into projects)

## Configuration

Each project stores Confluence config in `.claude/confluence.json`:

```json
{
  "confluence_url": "https://your-confluence.atlassian.net",
  "space_key": "PROJ",
  "page_title": "Project Overview"
}
```

## Output

Saves to project's `.claude/` directory:
- `project-context.json` — Structured context object
- `project-context.md` — Human-readable summary

## Context Object Fields

- `project_name`: string
- `business_value`: string — Why this project exists, strategic importance
- `stakeholders`: string[] — Teams, people involved
- `constraints`: string[] — Business/technical/timeline constraints
- `business_processes`: string[] — Key processes this enables or changes
- `confluence_source`: string — URL to source
- `last_updated`: ISO date string

Missing fields trigger interactive prompts during skill execution.
