#!/usr/bin/env python3
"""
Confluence Context Extractor

Fetches project context from Confluence and structures it for agent briefings.
Usage: python confluence_context.py [--project-path /path/to/project]
"""

import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
from subprocess import run, CalledProcessError, PIPE
import tempfile


def load_confluence_config(project_path: Path) -> Dict[str, str]:
    """Load Confluence configuration from .claude/confluence.json"""
    config_path = project_path / ".claude" / "confluence.json"

    if not config_path.exists():
        print(f"❌ No Confluence config found at {config_path}")
        print("\nCreate .claude/confluence.json with:")
        print(json.dumps({
            "confluence_url": "https://your-confluence.atlassian.net",
            "space_key": "PROJ",
            "page_title": "Project Overview"
        }, indent=2))
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def verify_confluence_credentials() -> bool:
    """Check that Confluence credentials are set."""
    required = ["CONFLUENCE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"]
    missing = [var for var in required if not os.getenv(var)]

    if missing:
        print("❌ Missing Confluence credentials:")
        for var in missing:
            print(f"   • {var}")
        print("\nSet these environment variables, then try again:")
        print("   export CONFLUENCE_URL='https://your-org.atlassian.net/wiki'")
        print("   export CONFLUENCE_EMAIL='your.email@example.com'")
        print("   export CONFLUENCE_API_TOKEN='your-api-token-from-atlassian'")
        print("\nGet an API token at: https://id.atlassian.com/manage-profile/security/api-tokens")
        return False
    return True


def find_page_id_by_title(space: str, page_title: str) -> Optional[str]:
    """Look up page ID by space key and title using Confluence REST API."""
    import urllib.request
    import urllib.parse
    import base64

    conf_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
    email = os.getenv("CONFLUENCE_EMAIL")
    token = os.getenv("CONFLUENCE_API_TOKEN")

    if not (conf_url and email and token):
        return None

    # Confluence CQL query: find page by space key and title
    cql = f"space = {space} AND title ~ \"{page_title}\""
    api_url = f"{conf_url}/rest/api/content?cql={urllib.parse.quote(cql)}&limit=1"

    # Basic auth
    auth_str = f"{email}:{token}"
    auth_bytes = base64.b64encode(auth_str.encode()).decode()

    try:
        req = urllib.request.Request(
            api_url,
            headers={"Authorization": f"Basic {auth_bytes}"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            if data.get("results"):
                return data["results"][0]["id"]
    except Exception as e:
        print(f"⚠️  Could not look up page ID: {e}")

    return None


def fetch_confluence_markdown(conf_config: Dict[str, str]) -> str:
    """Fetch Confluence page as Markdown using mdc command."""
    # Determine page ID
    page_id = conf_config.get("page_id")

    if not page_id:
        # Look up by space and title
        space = conf_config.get("space_key")
        title = conf_config.get("page_title")

        if not (space and title):
            raise ValueError("Config must have either 'page_id' or both 'space_key' and 'page_title'")

        print(f"📖 Looking up page ID: {space}/{title}...")
        page_id = find_page_id_by_title(space, title)

        if not page_id:
            raise ValueError(f"Could not find page: {space}/{title}")

        print(f"   Found page ID: {page_id}")

    # Fetch using mdc
    print(f"📥 Fetching from Confluence (page ID: {page_id})...")

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = run(
            ["mdc", "fetch", "--page-id", page_id, "-o", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"mdc fetch failed: {result.stderr}")

        with open(tmp_path) as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def extract_field(content: str, field_name: str, patterns: List[str]) -> Optional[str]:
    """Extract field from markdown content using regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return None


def parse_confluence_content(content: str) -> Dict[str, Any]:
    """Parse Confluence markdown to extract context fields."""

    patterns = {
        "business_value": [
            r"## Business Value\s*\n(.*?)(?=##|\Z)",
            r"## Why\s*\n(.*?)(?=##|\Z)",
            r"## Strategic Impact\s*\n(.*?)(?=##|\Z)",
            r"### Business Value\s*\n(.*?)(?=###|\Z)",
        ],
        "stakeholders": [
            r"## Stakeholders?\s*\n(.*?)(?=##|\Z)",
            r"## Teams?\s*\n(.*?)(?=##|\Z)",
            r"### Stakeholders?\s*\n(.*?)(?=###|\Z)",
        ],
        "constraints": [
            r"## Constraints?\s*\n(.*?)(?=##|\Z)",
            r"## Timeline\s*\n(.*?)(?=##|\Z)",
            r"### Constraints?\s*\n(.*?)(?=###|\Z)",
        ],
        "business_processes": [
            r"## (Business )?Processes?\s*\n(.*?)(?=##|\Z)",
            r"## What (this|the project) (enables?|does)\s*\n(.*?)(?=##|\Z)",
            r"### (Business )?Processes?\s*\n(.*?)(?=###|\Z)",
        ],
    }

    extracted = {}
    for field, field_patterns in patterns.items():
        value = extract_field(content, field, field_patterns)
        if value:
            # Clean up extracted content
            value = re.sub(r'\n\s*\n', '\n', value).strip()
            # For list fields, try to parse as bullet points
            if field in ["stakeholders", "constraints", "business_processes"]:
                lines = [line.strip().lstrip('- ').lstrip('* ')
                        for line in value.split('\n')
                        if line.strip() and not line.strip().startswith('#')]
                extracted[field] = [l for l in lines if l][:10]  # Limit to 10 items
            else:
                extracted[field] = value[:500]  # Limit text fields

    return extracted


def is_interactive() -> bool:
    """Check if running in interactive mode."""
    return sys.stdin.isatty()


def prompt_for_field(field_name: str, field_type: str = "string", interactive: bool = True) -> Any:
    """Prompt user for missing field. Returns None if not interactive or user skips."""
    if not interactive:
        return None

    friendly_names = {
        "business_value": "Business Value (why this project exists)",
        "stakeholders": "Stakeholders (teams/people involved)",
        "constraints": "Constraints (business/tech/timeline)",
        "business_processes": "Business Processes (what this enables)",
    }

    display_name = friendly_names.get(field_name, field_name)
    print(f"\n❓ {display_name}")

    if field_type == "list":
        print("   (Enter items one per line, empty line to finish)")
        items = []
        while True:
            try:
                item = input(f"   • ").strip()
                if not item:
                    break
                items.append(item)
            except EOFError:
                break
        return items if items else None
    else:
        print("   (Enter value, or press Enter to skip)")
        try:
            return input(f"   > ").strip() or None
        except EOFError:
            return None


def build_context_object(
    project_name: str,
    extracted: Dict[str, Any],
    confluence_config: Dict[str, str],
    confluence_url: Optional[str] = None,
    interactive: bool = True
) -> Dict[str, Any]:
    """Build the structured context object, prompting for missing fields."""

    context = {
        "project_name": project_name,
        "business_value": None,
        "stakeholders": [],
        "constraints": [],
        "business_processes": [],
        "confluence_source": confluence_url or "",
        "last_updated": datetime.now().isoformat(),
    }

    # Fill in extracted values
    context.update(extracted)

    # Prompt for missing fields (only if interactive)
    if interactive:
        print("\n" + "="*60)
        print("Building Project Context")
        print("="*60)

        # Business value (required in interactive mode)
        if not context.get("business_value"):
            context["business_value"] = prompt_for_field("business_value", "string", interactive)

        # Stakeholders
        if not context.get("stakeholders"):
            stakeholders = prompt_for_field("stakeholders", "list", interactive)
            if stakeholders:
                context["stakeholders"] = stakeholders

        # Constraints
        if not context.get("constraints"):
            constraints = prompt_for_field("constraints", "list", interactive)
            if constraints:
                context["constraints"] = constraints

        # Business processes
        if not context.get("business_processes"):
            processes = prompt_for_field("business_processes", "list", interactive)
            if processes:
                context["business_processes"] = processes
    else:
        print("⏭️  Skipping interactive prompts (non-interactive mode)")
        if not context.get("business_value"):
            print("   ℹ️  Business value: (not set)")
        if not context.get("stakeholders"):
            print("   ℹ️  Stakeholders: (not set)")
        if not context.get("constraints"):
            print("   ℹ️  Constraints: (not set)")
        if not context.get("business_processes"):
            print("   ℹ️  Business processes: (not set)")

    return context


def generate_markdown_summary(context: Dict[str, Any]) -> str:
    """Generate human-readable markdown summary from context."""

    md = f"""# {context['project_name']} — Project Context

**Last Updated:** {context['last_updated']}

## Business Value

{context.get('business_value', '(Not specified)')}

## Stakeholders

{format_list(context.get('stakeholders', []))}

## Constraints

{format_list(context.get('constraints', []))}

## Business Processes

{format_list(context.get('business_processes', []))}

---

**Source:** {context.get('confluence_source', 'Manual entry')}

*This context is cached locally. To update, run the confluence-context skill again.*
"""
    return md


def format_list(items: List[str]) -> str:
    """Format list for markdown."""
    if not items:
        return "(None specified)"
    return "\n".join(f"- {item}" for item in items)


def save_context(project_path: Path, context: Dict[str, Any], markdown: str) -> None:
    """Save context object and markdown summary."""
    claude_dir = project_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # Save JSON
    json_path = claude_dir / "project-context.json"
    with open(json_path, 'w') as f:
        json.dump(context, f, indent=2)
    print(f"✅ Saved context: {json_path}")

    # Save markdown
    md_path = claude_dir / "project-context.md"
    with open(md_path, 'w') as f:
        f.write(markdown)
    print(f"✅ Saved summary: {md_path}")


def main():
    project_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        sys.exit(1)

    project_name = project_path.name

    print(f"\n🔄 Extracting context for: {project_name}")
    print(f"   Project path: {project_path}\n")

    # Load configuration
    confluence_config = load_confluence_config(project_path)

    # Check credentials
    if not verify_confluence_credentials():
        print("\n⚠️  Confluence credentials not configured. Skipping fetch.")
        content = ""
    else:
        # Fetch content from Confluence
        try:
            content = fetch_confluence_markdown(confluence_config)
        except Exception as e:
            print(f"⚠️  Could not fetch from Confluence: {e}")
            content = ""

    # Parse content
    extracted = parse_confluence_content(content)
    print(f"📊 Extracted fields: {', '.join(extracted.keys())}\n")

    # Build context, prompting for missing fields
    # Construct confluence URL (with space info if available)
    confluence_url = confluence_config['confluence_url']
    if 'space_key' in confluence_config:
        confluence_url = f"{confluence_url}/spaces/{confluence_config['space_key']}"
    if 'page_id' in confluence_config:
        confluence_url = f"{confluence_url}/pages/{confluence_config['page_id']}"

    interactive = is_interactive()
    context = build_context_object(project_name, extracted, confluence_config, confluence_url, interactive)

    # Generate markdown
    markdown = generate_markdown_summary(context)

    # Save
    save_context(project_path, context, markdown)

    print("\n✨ Context extraction complete!")
    print(f"\nTo use this in agents, reference: .claude/project-context.json")


if __name__ == "__main__":
    main()
