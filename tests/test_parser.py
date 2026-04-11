import pytest
from pathlib import Path
from trimr.parser import (
    has_frontmatter,
    extract_frontmatter,
    is_skill_file,
    extract_skill_body,
    get_skill_description,
    get_skill_name,
)


class TestLineOneRule:
    """CRITICAL: Test the line 1 rule enforcer (--- at byte offset 0)."""

    def test_valid_frontmatter_at_line_1(self):
        """Valid frontmatter starts with --- on line 1."""
        content = "---\nname: Test\ndescription: Test skill\n---\nBody content"
        assert has_frontmatter(content) is True

    def test_frontmatter_with_blank_line_before_rejected(self):
        """CRITICAL: File with blank line before --- should be rejected."""
        content = "\n---\nname: Test\ndescription: Test skill\n---\nBody"
        assert has_frontmatter(content) is False

    def test_frontmatter_with_spaces_before_rejected(self):
        """CRITICAL: File with spaces before --- should be rejected."""
        content = "   ---\nname: Test\ndescription: Test skill\n---\nBody"
        assert has_frontmatter(content) is False

    def test_frontmatter_missing_opening(self):
        """Missing opening --- should be rejected."""
        content = "name: Test\ndescription: Test skill\n---\nBody"
        assert has_frontmatter(content) is False

    def test_frontmatter_missing_closing(self):
        """Missing closing --- should be rejected."""
        content = "---\nname: Test\ndescription: Test skill\nBody"
        assert has_frontmatter(content) is False

    def test_frontmatter_empty_file(self):
        """Empty file should not have frontmatter."""
        assert has_frontmatter("") is False

    def test_frontmatter_only_opening(self):
        """File with only opening --- should be rejected."""
        content = "---"
        assert has_frontmatter(content) is False


class TestFrontmatterExtraction:
    """Test frontmatter extraction functionality."""

    def test_extract_valid_frontmatter(self):
        """Extract valid YAML frontmatter."""
        content = "---\nname: Test\ndescription: Test skill\n---\nBody"
        fm = extract_frontmatter(content)
        assert fm is not None
        assert fm["name"] == "Test"
        assert fm["description"] == "Test skill"

    def test_extract_frontmatter_invalid_yaml(self):
        """Invalid YAML in frontmatter returns None."""
        content = "---\ninvalid: yaml: content:\n---\nBody"
        fm = extract_frontmatter(content)
        assert fm is None

    def test_extract_frontmatter_no_frontmatter(self):
        """File without frontmatter returns None."""
        content = "Just some content"
        fm = extract_frontmatter(content)
        assert fm is None

    def test_extract_frontmatter_blank_line_before(self):
        """Frontmatter with blank line before returns None."""
        content = "\n---\nname: Test\n---\nBody"
        fm = extract_frontmatter(content)
        assert fm is None


class TestSkillFileDetection:
    """Test skill file detection."""

    def test_is_skill_file_valid(self):
        """Valid skill file with name and description."""
        content = "---\nname: PDF Tool\ndescription: Handles PDF files\n---\nBody"
        path = Path("skills/pdf/SKILL.md")
        assert is_skill_file(path, content) is True

    def test_is_skill_file_missing_name(self):
        """File without name field is not a skill."""
        content = "---\ndescription: Handles PDF files\n---\nBody"
        path = Path("skills/pdf/SKILL.md")
        assert is_skill_file(path, content) is False

    def test_is_skill_file_missing_description(self):
        """File without description field is not a skill."""
        content = "---\nname: PDF Tool\n---\nBody"
        path = Path("skills/pdf/SKILL.md")
        assert is_skill_file(path, content) is False

    def test_is_skill_file_no_frontmatter(self):
        """File without frontmatter is not a skill."""
        content = "# Just a markdown file\n\nNo frontmatter here."
        path = Path("skills/pdf/SKILL.md")
        assert is_skill_file(path, content) is False

    def test_is_skill_file_wrong_extension(self):
        """Non-markdown file is not a skill."""
        content = "---\nname: Test\ndescription: Test\n---\nBody"
        path = Path("skills/test.txt")
        assert is_skill_file(path, content) is False

    def test_is_skill_file_blank_line_before_delimiters(self):
        """CRITICAL: File with blank line before --- is not a skill."""
        content = "\n---\nname: Test\ndescription: Test\n---\nBody"
        path = Path("skills/test/SKILL.md")
        assert is_skill_file(path, content) is False


class TestSkillBodyExtraction:
    """Test skill body extraction."""

    def test_extract_skill_body(self):
        """Extract body content after frontmatter."""
        content = "---\nname: Test\ndescription: Test\n---\nBody content here"
        body = extract_skill_body(content)
        assert body == "Body content here"

    def test_extract_skill_body_no_frontmatter(self):
        """Without frontmatter, entire content is body."""
        content = "No frontmatter here\nJust content"
        body = extract_skill_body(content)
        assert body == content


class TestSkillMetadata:
    """Test skill metadata extraction."""

    def test_get_skill_description(self):
        """Extract skill description from frontmatter."""
        fm = {"name": "Test", "description": "This is a test skill"}
        desc = get_skill_description(fm)
        assert desc == "This is a test skill"

    def test_get_skill_description_empty(self):
        """Return empty string if description missing."""
        fm = {"name": "Test"}
        desc = get_skill_description(fm)
        assert desc == ""

    def test_get_skill_description_none_frontmatter(self):
        """Return empty string for None frontmatter."""
        desc = get_skill_description(None)
        assert desc == ""

    def test_get_skill_name(self):
        """Extract skill name from frontmatter."""
        fm = {"name": "PDF Tool", "description": "Processes PDFs"}
        name = get_skill_name(fm)
        assert name == "PDF Tool"

    def test_get_skill_name_empty(self):
        """Return empty string if name missing."""
        fm = {"description": "Test"}
        name = get_skill_name(fm)
        assert name == ""

    def test_get_skill_name_none_frontmatter(self):
        """Return empty string for None frontmatter."""
        name = get_skill_name(None)
        assert name == ""
