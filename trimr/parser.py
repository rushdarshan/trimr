import yaml
from typing import Optional, Dict, Any
from pathlib import Path


def has_frontmatter(content: str) -> bool:
    """
    Check if content has valid YAML frontmatter.
    
    CRITICAL: --- MUST appear at byte offset 0 (line 1, column 0).
    No lenient parsing. Rejects files where --- appears on line 2+.
    """
    if not content:
        return False
    
    if not content.startswith("---"):
        return False
    
    lines = content.split("\n", 2)
    if len(lines) < 2:
        return False
    
    if lines[0] != "---":
        return False
    
    closing_index = content.find("\n---\n", 4)
    if closing_index == -1:
        return False
    
    return True


def has_malformed_frontmatter(content: str) -> bool:
    """
    Check if content has frontmatter NOT at line 1 (Flaw 5 fix).
    Detects patterns like:
    - # Title
      ---
      name: ...
    - Blank line before ---
    """
    if not content:
        return False
    
    lines = content.split("\n", 3)
    if len(lines) < 2:
        return False
    
    # Line 1 is not ---, but --- appears somewhere in first 3 lines
    if lines[0] != "---":
        for i in range(min(3, len(lines))):
            if lines[i].strip() == "---":
                # Check if it looks like a closing --- (would indicate frontmatter below)
                if i > 0:
                    return True
    
    return False


def extract_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """
    Extract YAML frontmatter from content.
    
    Returns dict if valid frontmatter exists at line 1, None otherwise.
    Strict parsing: no lenient fallbacks.
    """
    if not has_frontmatter(content):
        return None
    
    start = content.find("---")
    if start != 0:
        return None
    
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    
    frontmatter_text = content[4:end]
    
    try:
        data = yaml.safe_load(frontmatter_text)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


def is_skill_file(file_path: Path, content: Optional[str] = None) -> bool:
    """
    Detect if file is a skill file.
    
    Criteria:
    - Has valid frontmatter (--- on line 1)
    - Contains 'name' field
    - Contains 'description' field
    """
    if not file_path.suffix.lower() in [".md", ".markdown"]:
        return False
    
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False
    
    frontmatter = extract_frontmatter(content)
    if frontmatter is None:
        return False
    
    return "name" in frontmatter and "description" in frontmatter


def extract_skill_body(content: str) -> str:
    """Extract content after frontmatter (skill body)."""
    if not has_frontmatter(content):
        return content
    
    end = content.find("\n---\n", 4)
    if end == -1:
        return content
    
    return content[end + 5:].lstrip()


def get_skill_description(frontmatter: Optional[Dict[str, Any]]) -> str:
    """Get skill description from frontmatter, or empty string if not present."""
    if frontmatter is None:
        return ""
    return str(frontmatter.get("description", "")).strip()


def get_skill_name(frontmatter: Optional[Dict[str, Any]]) -> str:
    """Get skill name from frontmatter, or empty string if not present."""
    if frontmatter is None:
        return ""
    return str(frontmatter.get("name", "")).strip()
