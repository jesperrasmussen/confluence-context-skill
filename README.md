# Confluence Context Skill

Extract and structure project context from Confluence documentation to build intelligent agent briefs.

## Overview

This skill bridges the gap between what's in your codebase and the business/process context stored in Confluence. It:

- **Fetches** documentation from Confluence
- **Extracts** key business context (stakeholders, constraints, business value, processes)
- **Structures** it as JSON for programmatic access
- **Generates** human-readable summaries for agent briefings
- **Auto-loads** when you open a project
- **Allows** other agents to query the cached context

## Quick Start

### 1. Install

```bash
# Clone/copy this project
cd /path/to/this/project

# Copy skill to Claude Code global skills
cp confluence_context.py ~/.claude/skills/confluence-context
chmod +x ~/.claude/skills/confluence-context
```

### 2. Set Confluence Credentials

The skill uses the `mdc` command (from `confluence-markdown` skill) to fetch pages. Set these environment variables:

```bash
export CONFLUENCE_URL="https://your-org.atlassian.net/wiki"
export CONFLUENCE_EMAIL="your.email@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
```

**Get an API token:**
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy and store securely

**To persist these** (add to `.zshrc`, `.bashrc`, etc.):

```bash
export CONFLUENCE_URL="https://your-org.atlassian.net/wiki"
export CONFLUENCE_EMAIL="your.email@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
```

### 3. Configure Your Project

In your project directory, create `.claude/confluence.json`:

```bash
mkdir -p .claude
cat > .claude/confluence.json << 'EOF'
{
  "confluence_url": "https://your-org.atlassian.net/wiki",
  "space_key": "PROJKEY",
  "page_title": "Project Overview"
}
EOF
```

**Alternative:** Use page ID directly (if you know it):

```json
{
  "confluence_url": "https://your-org.atlassian.net/wiki",
  "page_id": "123456789"
}
```

### 4. Run the Skill

From Claude Code:

```
/confluence-context /path/to/your/project
```

The skill will:
1. Fetch content from Confluence
2. Extract business context fields
3. **Prompt you** for any fields it couldn't auto-extract
4. Save structured JSON and markdown to `.claude/`

## What Gets Extracted

The skill looks for these sections in Confluence:

- **Business Value** — Why the project exists, strategic importance
- **Stakeholders** — Teams and people involved
- **Constraints** — Business, technical, or timeline constraints
- **Business Processes** — What this enables or changes

Missing fields trigger interactive prompts.

## Output Files

After running, your `.claude/` directory contains:

### `project-context.json`

Structured context for programmatic access:

```json
{
  "project_name": "my-project",
  "business_value": "Enables real-time analytics for customer behavior...",
  "stakeholders": ["Data Team", "Analytics Platform Team", "VP Product"],
  "constraints": ["Must handle 1M+ events/day", "HIPAA compliance required"],
  "business_processes": ["Customer journey analysis", "Churn prediction"],
  "confluence_source": "https://...",
  "last_updated": "2026-11-03T10:30:00"
}
```

### `project-context.md`

Human-readable summary for agent briefs.

## Using Context in Your Project

### In Code/Scripts

```python
import json

with open(".claude/project-context.json") as f:
    context = json.load(f)
    print(f"Business value: {context['business_value']}")
```

### In Agent Briefs

Include context when spawning agents:

```python
import json

with open(".claude/project-context.json") as f:
    context = json.load(f)

agent_brief = f"""
Project: {context['project_name']}

Business Goal: {context['business_value']}

Key Stakeholders: {', '.join(context['stakeholders'])}

Constraints: {', '.join(context['constraints'])}

You are working on a project that enables: {', '.join(context['business_processes'])}
"""
```

### Auto-Load on Project Open

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "on-project-open": "python ~/.claude/skills/confluence-context"
  }
}
```

This automatically refreshes context when you switch to the project.

## Integration

See [INTEGRATION.md](INTEGRATION.md) for detailed setup instructions including:
- Installation options
- Configuration reference
- Skill registration
- Hook setup
- Using context in agent system prompts

## Updating Context

Re-run the skill when Confluence docs change:

```
/confluence-context /path/to/your/project
```

The skill intelligently merges changes:
- **Auto-extracted values** update automatically
- **Manually-entered values** are preserved unless explicitly changed
- **New fields** trigger prompts as before

## How It Works

1. **Reads config** from `.claude/confluence.json`
2. **Fetches** the Confluence page as Markdown
3. **Parses** with regex patterns to find context sections
4. **Extracts** structured fields (business value, stakeholders, etc.)
5. **Prompts** for any missing required fields
6. **Saves** JSON (for tools) and Markdown (for humans)

The extraction is heuristic-based, so your Confluence page should follow standard section headings. It handles common variations like `## Business Value`, `### Why`, `## Strategic Impact`, etc.

## Troubleshooting

**"No Confluence config found"**
- Create `.claude/confluence.json` in your project
- Copy from `confluence.json.example` as a template

**"Could not fetch from Confluence"**
- Verify the Confluence URL, space key, and page title
- Check that you have access to the page
- Try fetching manually via the `confluence-markdown` skill

**Missing fields in extraction**
- Ensure Confluence page uses standard heading levels (`##`, `###`)
- Check that section titles match the patterns the skill searches for
- You can always fill in manually when prompted

## Architecture

The skill is designed to be:

- **Modular** — Use the JSON context anywhere, not just Claude Code
- **Non-invasive** — Works alongside existing project structure
- **Updatable** — Re-run anytime to refresh from Confluence
- **Agent-accessible** — Other tools/agents can read the cached context
- **Interactive** — Lets you customize context beyond what Confluence has

## License

MIT
