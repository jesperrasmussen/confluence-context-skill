# Integration Guide

## Prerequisites

This skill uses the `mdc` command from the `confluence-markdown` skill. You need:

1. **mdc installed** — from `confluence-markdown` skill (`command -v mdc`)
2. **Confluence API token** — from https://id.atlassian.com/manage-profile/security/api-tokens
3. **Environment variables set:**

```bash
export CONFLUENCE_URL="https://your-org.atlassian.net/wiki"
export CONFLUENCE_EMAIL="your.email@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
```

## Setup

### 1. Copy Skill to Claude Code

Copy the skill to your Claude Code configuration:

```bash
# Option A: Copy to global skills
cp confluence_context.py ~/.claude/skills/confluence-context

# Option B: Copy to project skills
cp confluence_context.py /path/to/your/project/.claude/skills/confluence-context
```

Make it executable:
```bash
chmod +x ~/.claude/skills/confluence-context
```

### 2. Configure Per-Project

In each project using this skill, create `.claude/confluence.json`:

```bash
mkdir -p /path/to/project/.claude
cp confluence.json.example /path/to/project/.claude/confluence.json
```

Edit to point to your Confluence space. Use either **space + title** (script looks up ID):

```json
{
  "confluence_url": "https://your-org.atlassian.net/wiki",
  "space_key": "PROJKEY",
  "page_title": "Project Overview",
  "max_depth": 1
}
```

Or **page ID directly** (fastest):

```json
{
  "confluence_url": "https://your-org.atlassian.net/wiki",
  "page_id": "123456789",
  "max_depth": 1
}
```

**Multi-page context:** Set `max_depth` to traverse child pages:
- `max_depth: 1` — Only the root page
- `max_depth: 2` — Root + immediate children
- `max_depth: 3` — Root + children + grandchildren

All fetched pages are concatenated and re-parsed as one context.

### 3. Run Manually

From Claude Code, use the skill:

```
/confluence-context /path/to/project
```

Or from the project directory:

```
python confluence_context.py
```

## Output

Creates in `.claude/`:

- **project-context.json** — Structured data for programmatic access
- **project-context.md** — Human-readable summary

## Usage in Agents

### Reading Context in Code

```python
import json
from pathlib import Path

context_path = Path(".claude/project-context.json")
if context_path.exists():
    with open(context_path) as f:
        context = json.load(f)
        print(context["business_value"])
```

### Via Environment/Memory Hook

Add to `.claude/settings.json` to auto-load on project open:

```json
{
  "hooks": {
    "on-project-open": "python ~/.claude/skills/confluence-context"
  }
}
```

This will automatically update context when opening the project.

### Agent System Prompts

Include context in agent briefing prompts:

```
Project context: {project_name}
Business value: {business_value}
Stakeholders: {stakeholders}
Key constraints: {constraints}
```

## Updating Context

Re-run the skill whenever Confluence docs change:

```
/confluence-context /path/to/project
```

It will merge new extracted values with manually-provided ones, only prompting for fields that are still missing.
