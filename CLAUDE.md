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

## Prerequisites

**Required:**
- `mdc` command available (from `confluence-markdown` skill)
- Confluence API credentials as environment variables:
  - `CONFLUENCE_URL`
  - `CONFLUENCE_EMAIL`
  - `CONFLUENCE_API_TOKEN`

**Optional but recommended:**
- `ANTHROPIC_API_KEY` environment variable
- `anthropic` Python package (`pip3 install anthropic`)
- Enables intelligent Claude-powered context extraction instead of regex

## Configuration

Each project stores Confluence config in `.claude/confluence.json`. Two options:

**Option 1: Space key + page title** (script looks up page ID):
```json
{
  "confluence_url": "https://your-confluence.atlassian.net/wiki",
  "space_key": "PROJ",
  "page_title": "Project Overview"
}
```

**Option 2: Page ID directly** (simpler if you know it):
```json
{
  "confluence_url": "https://your-confluence.atlassian.net/wiki",
  "page_id": "123456789"
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
