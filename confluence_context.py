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
from typing import Optional, Dict, List, Any, Set
from subprocess import run, CalledProcessError, PIPE
import tempfile
import urllib.request
import urllib.parse
import base64

try:
    from anthropic import Anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False


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


def _confluence_api_auth() -> Optional[str]:
    """Get Basic auth header for Confluence API."""
    email = os.getenv("CONFLUENCE_EMAIL")
    token = os.getenv("CONFLUENCE_API_TOKEN")
    if not (email and token):
        return None
    auth_str = f"{email}:{token}"
    auth_bytes = base64.b64encode(auth_str.encode()).decode()
    return f"Basic {auth_bytes}"


def _confluence_api_request(url: str) -> Optional[Dict]:
    """Make a Confluence REST API request."""
    auth = _confluence_api_auth()
    if not auth:
        return None

    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": auth}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"⚠️  API request failed: {e}")
        return None


def find_page_id_by_title(space: str, page_title: str) -> Optional[str]:
    """Look up page ID by space key and title using Confluence REST API."""
    conf_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
    if not conf_url:
        return None

    cql = f"space = {space} AND title ~ \"{page_title}\""
    api_url = f"{conf_url}/rest/api/content?cql={urllib.parse.quote(cql)}&limit=1"

    data = _confluence_api_request(api_url)
    if data and data.get("results"):
        return data["results"][0]["id"]
    return None


def get_page_hierarchy(page_id: str) -> Dict[str, Any]:
    """Get page info including ancestors and children."""
    conf_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
    if not conf_url:
        return {}

    api_url = f"{conf_url}/rest/api/content/{page_id}?expand=ancestors,children.page"
    return _confluence_api_request(api_url) or {}


def traverse_page_hierarchy(
    page_id: str,
    max_depth: int = 2,
    visited: Optional[Set[str]] = None,
    current_depth: int = 0
) -> List[str]:
    """Traverse page hierarchy to collect related page IDs (children and siblings).

    Returns list of page IDs to fetch, up to max_depth.
    ponytail: simple BFS, no memoization of full trees. Upgrade if tree traversal becomes bottleneck.
    """
    if visited is None:
        visited = set()

    if page_id in visited or current_depth >= max_depth:
        return []

    visited.add(page_id)
    pages_to_fetch = [page_id]

    if current_depth >= max_depth:
        return pages_to_fetch

    try:
        # Get page info and children
        hierarchy = get_page_hierarchy(page_id)
        if not hierarchy:
            return pages_to_fetch

        # Helper to extract page list from Confluence API response
        def get_pages_from_children(children_container):
            """Extract page list from children.page structure."""
            if not isinstance(children_container, dict):
                return []
            page_container = children_container.get("page")
            if isinstance(page_container, dict):
                return page_container.get("results", [])
            elif isinstance(page_container, list):
                return page_container
            return []

        # Traverse children
        children_container = hierarchy.get("children")
        for child in get_pages_from_children(children_container):
            child_id = child.get("id")
            if child_id and child_id not in visited:
                pages_to_fetch.extend(
                    traverse_page_hierarchy(child_id, max_depth, visited, current_depth + 1)
                )

        # Traverse siblings (pages with same parent)
        ancestors = hierarchy.get("ancestors", [])
        if ancestors and current_depth == 0:  # Only get siblings at root level
            parent_id = ancestors[-1].get("id") if ancestors else None
            if parent_id:
                parent_info = get_page_hierarchy(parent_id)
                if isinstance(parent_info, dict):
                    for sibling in get_pages_from_children(parent_info.get("children")):
                        sibling_id = sibling.get("id")
                        if sibling_id and sibling_id not in visited:
                            pages_to_fetch.append(sibling_id)
    except Exception as e:
        print(f"⚠️  Error traversing hierarchy: {e}")

    return pages_to_fetch


def _fetch_single_page(page_id: str) -> Optional[str]:
    """Fetch a single page as Markdown using mdc."""
    # Use a unique temporary file name
    import uuid
    tmp_path = f"/tmp/confluence_{uuid.uuid4().hex}.md"

    try:
        result = run(
            ["mdc", "fetch", "--page-id", page_id, "-o", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"      ❌ mdc failed: {result.stderr.strip()[:100]}")
            return None

        # Read the file
        try:
            with open(tmp_path, 'r') as f:
                content = f.read()
                if content:
                    print(f"      ✓ fetched {len(content)} bytes")
                    return content
                else:
                    print(f"      ❌ output file is empty")
                    return None
        except Exception as e:
            print(f"      ❌ could not read output: {e}")
            return None
    except Exception as e:
        print(f"      ❌ {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass


def fetch_confluence_markdown(conf_config: Dict[str, str]) -> str:
    """Fetch Confluence page(s) as Markdown using mdc command.

    Supports single page or multi-page traversal based on config.
    """
    # Determine root page ID
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

    # Determine if we should traverse hierarchy
    max_depth = int(conf_config.get("max_depth", 1))
    if max_depth > 1:
        print(f"🔗 Traversing hierarchy (max depth: {max_depth})...")
        page_ids = traverse_page_hierarchy(page_id, max_depth)
        print(f"   Found {len(page_ids)} pages to fetch")
    else:
        page_ids = [page_id]

    # Fetch all pages
    print(f"📥 Fetching from Confluence ({len(page_ids)} page(s))...")
    all_content = []

    for i, pid in enumerate(page_ids, 1):
        print(f"   [{i}/{len(page_ids)}] Fetching page {pid}...")
        content = _fetch_single_page(pid)
        if content:
            all_content.append(content)

    if not all_content:
        raise RuntimeError("Could not fetch any pages from Confluence")

    # Concatenate content
    if len(all_content) > 1:
        print(f"   ✓ Concatenating {len(all_content)} pages")
        return "\n\n---\n\n".join(all_content)
    else:
        return all_content[0]


def extract_field(content: str, field_name: str, patterns: List[str]) -> Optional[str]:
    """Extract field from markdown content using regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return None


def analyze_content_with_claude(content: str, project_name: str) -> Dict[str, Any]:
    """Use Claude to intelligently extract business context from Confluence content."""
    if not CLAUDE_AVAILABLE:
        return {}

    # Support both direct API key and gateway auth token
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        print("   ℹ️  ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set, skipping Claude analysis")
        return {}

    # Support custom base URL for AI gateway
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    client = Anthropic(api_key=api_key, base_url=base_url) if base_url else Anthropic(api_key=api_key)
    print(f"   🤖 Analyzing with Claude{'@gateway' if base_url else ''}...")

    prompt = f"""Analyze the following Confluence documentation for the project "{project_name}" and extract the business context.

Return a JSON object with these fields:
- business_value (string): Why this project exists, its strategic importance, and the problem it solves
- stakeholders (array): Teams, departments, or roles involved in this project
- constraints (array): Business, technical, timeline, or regulatory constraints
- business_processes (array): Key processes this project enables, supports, or changes

Only include information that's clearly present in the documentation. If a field is not mentioned, use null or empty array.

Be concise but specific. For arrays, return 3-5 items maximum.

CONFLUENCE CONTENT:
---
{content[:8000]}  # Limit to first 8000 chars to stay within token budget
---

Return only valid JSON, no markdown formatting."""

    try:
        print("   🤖 Analyzing content with Claude...")
        message = client.messages.create(
            model="claude-opus-5-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Parse the response
        response_text = message.content[0].text
        # Try to extract JSON if Claude wrapped it in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        result = json.loads(response_text)
        print("   ✓ Claude extracted context")
        return result

    except Exception as e:
        print(f"   ⚠️  Claude analysis failed: {e}")
        return {}


def parse_confluence_content(content: str, project_name: str) -> Dict[str, Any]:
    """Parse Confluence content using Claude for intelligent extraction."""
    # Try Claude first if available
    extracted = analyze_content_with_claude(content, project_name)
    if extracted:
        return extracted

    # Fallback to regex if Claude unavailable
    print("   ⏭️  Falling back to regex extraction")
    patterns = {
        "business_value": [
            r"## Business Value\s*\n(.*?)(?=##|\Z)",
            r"## Why\s*\n(.*?)(?=##|\Z)",
            r"## Strategic Impact\s*\n(.*?)(?=##|\Z)",
        ],
        "stakeholders": [
            r"## Stakeholders?\s*\n(.*?)(?=##|\Z)",
            r"## Teams?\s*\n(.*?)(?=##|\Z)",
        ],
        "constraints": [
            r"## Constraints?\s*\n(.*?)(?=##|\Z)",
            r"## Requirements\s*\n(.*?)(?=##|\Z)",
        ],
        "business_processes": [
            r"## (Business )?Processes?\s*\n(.*?)(?=##|\Z)",
            r"## Features?\s*\n(.*?)(?=##|\Z)",
        ],
    }

    extracted = {}
    for field, field_patterns in patterns.items():
        value = extract_field(content, field, field_patterns)
        if value:
            value = re.sub(r'\n\s*\n', '\n', value).strip()
            if field in ["stakeholders", "constraints", "business_processes"]:
                lines = [line.strip().lstrip('- ').lstrip('* ')
                        for line in value.split('\n')
                        if line.strip() and not line.strip().startswith('#')]
                extracted[field] = [l for l in lines if l][:5]
            else:
                extracted[field] = value[:500]

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


def build_graphify_graph(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert project context to Graphify graph format.

    Returns a graph structure compatible with Graphify's graph.json schema.
    ponytail: simple node/edge structure without complex clustering.
    """
    nodes = []
    edges = []
    node_id = 0

    # Root project node
    project_node_id = node_id
    nodes.append({
        "id": node_id,
        "type": "Project",
        "label": context.get("project_name", "Unknown Project"),
        "properties": {
            "business_value": context.get("business_value", ""),
            "last_updated": context.get("last_updated", ""),
            "source": "confluence-context-skill"
        },
        "confidence": "EXTRACTED"
    })
    node_id += 1

    # Stakeholder nodes
    stakeholder_ids = []
    for stakeholder in context.get("stakeholders", []):
        stakeholder_ids.append(node_id)
        nodes.append({
            "id": node_id,
            "type": "Stakeholder",
            "label": stakeholder,
            "properties": {},
            "confidence": "EXTRACTED"
        })
        edges.append({
            "source": project_node_id,
            "target": node_id,
            "type": "hasStakeholder",
            "confidence": "EXTRACTED"
        })
        node_id += 1

    # Constraint nodes
    for constraint in context.get("constraints", []):
        nodes.append({
            "id": node_id,
            "type": "Constraint",
            "label": constraint,
            "properties": {},
            "confidence": "EXTRACTED"
        })
        edges.append({
            "source": project_node_id,
            "target": node_id,
            "type": "hasConstraint",
            "confidence": "EXTRACTED"
        })
        node_id += 1

    # Business process nodes
    for process in context.get("business_processes", []):
        nodes.append({
            "id": node_id,
            "type": "BusinessProcess",
            "label": process,
            "properties": {},
            "confidence": "EXTRACTED"
        })
        edges.append({
            "source": project_node_id,
            "target": node_id,
            "type": "enables",
            "confidence": "EXTRACTED"
        })
        node_id += 1

    return {
        "schema_version": "1.0",
        "graphify_version": "0.0.1",
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "source": "confluence-context-skill",
            "extracted_at": context.get("last_updated", ""),
            "project": context.get("project_name", "")
        }
    }


def save_graphify_graph(project_path: Path, graph: Dict[str, Any]) -> None:
    """Save Graphify graph to .claude/graph.json."""
    claude_dir = project_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    graph_path = claude_dir / "graph.json"
    with open(graph_path, 'w') as f:
        json.dump(graph, f, indent=2)
    print(f"✅ Saved Graphify graph: {graph_path}")


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
    extracted = parse_confluence_content(content, project_name)
    print(f"📊 Extracted fields: {', '.join(extracted.keys()) if extracted else '(none)'}\n")

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

    # Generate and save Graphify graph
    graph = build_graphify_graph(context)
    save_graphify_graph(project_path, graph)

    print("\n✨ Context extraction complete!")
    print(f"\nTo use this in agents, reference: .claude/project-context.json")
    print(f"For Graphify integration, use: .claude/graph.json")


if __name__ == "__main__":
    main()
