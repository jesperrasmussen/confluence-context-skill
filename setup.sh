#!/bin/bash
# Setup script for Confluence Context Skill

set -e

SKILL_DIR="${1:-.}"
SKILL_NAME="confluence-context"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"

echo "🔧 Setting up Confluence Context Skill"
echo "   Skill location: $SKILL_DIR"
echo "   Target: $CLAUDE_SKILLS_DIR/$SKILL_NAME"
echo ""

# Check if skill exists
if [ ! -f "$SKILL_DIR/confluence_context.py" ]; then
    echo "❌ Error: confluence_context.py not found in $SKILL_DIR"
    exit 1
fi

# Create skills directory if needed
mkdir -p "$CLAUDE_SKILLS_DIR"

# Copy skill
cp "$SKILL_DIR/confluence_context.py" "$CLAUDE_SKILLS_DIR/$SKILL_NAME"
chmod +x "$CLAUDE_SKILLS_DIR/$SKILL_NAME"

echo "✅ Skill installed to: $CLAUDE_SKILLS_DIR/$SKILL_NAME"
echo ""

# Prompt to configure a project
read -p "Configure a project now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Project path (default: current): " project_path
    project_path="${project_path:-.}"

    if [ ! -d "$project_path" ]; then
        echo "❌ Project path does not exist: $project_path"
        exit 1
    fi

    mkdir -p "$project_path/.claude"

    # Create config file
    read -p "Confluence URL (e.g., https://org.atlassian.net): " conf_url
    read -p "Space key (e.g., PROJ): " space_key
    read -p "Page title (e.g., Project Overview): " page_title

    cat > "$project_path/.claude/confluence.json" << EOF
{
  "confluence_url": "$conf_url",
  "space_key": "$space_key",
  "page_title": "$page_title"
}
EOF

    echo "✅ Configuration saved to: $project_path/.claude/confluence.json"
    echo ""
    echo "Next steps:"
    echo "  1. From Claude Code: /confluence-context $project_path"
    echo "  2. Or run: python $CLAUDE_SKILLS_DIR/$SKILL_NAME $project_path"
fi

echo ""
echo "📚 Documentation: https://github.com/your/repo (see README.md)"
echo "✨ Setup complete!"
