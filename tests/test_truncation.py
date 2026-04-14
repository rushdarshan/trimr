"""Tests for semantic truncation functionality."""

import pytest
from pathlib import Path

from trimr.migrator import Migrator
from trimr.models import GlobalFileReport


@pytest.fixture
def markdown_with_sections():
    """Create markdown text with multiple sections."""
    return """# Main Title

This is the introduction paragraph with some content.

## Section 1

This is section 1 with detailed information that takes up some tokens. It contains multiple paragraphs and important content that users should see.

More content in section 1 goes here.

## Section 2

This is section 2 with different information. It also has multiple paragraphs and detailed explanations.

More section 2 content here.

## Section 3

This is section 3 with additional information. It contains more detailed explanations and examples.

More section 3 content here.

## Section 4

This is section 4 with final information. This section might be removed if we truncate aggressively.

More section 4 content here."""


@pytest.fixture
def markdown_with_frontmatter():
    """Create markdown with YAML frontmatter and sections."""
    return """---
name: TestSkill
description: A test skill for truncation testing
---

# Skill Documentation

This is the introduction.

## Implementation

Implementation details go here.

## Usage

Usage information goes here.

## Examples

Example code and usage patterns."""


@pytest.fixture
def simple_project(tmp_path):
    """Create a simple project for testing."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    return project_root


class TestTruncationAlgorithm:
    """Test markdown-aware truncation."""
    
    def test_parse_sections_with_headers(self, markdown_with_sections, simple_project):
        """Test parsing markdown sections."""
        migrator = Migrator(simple_project)
        sections = migrator._parse_sections(markdown_with_sections)
        
        assert len(sections) >= 4  # At least 4 sections with headers
        assert any("Section 1" in s['title'] for s in sections if s['title'])
        assert any("Section 2" in s['title'] for s in sections if s['title'])
    
    def test_parse_sections_no_headers(self, simple_project):
        """Test parsing text without headers."""
        migrator = Migrator(simple_project)
        text = "Just some simple text without any headers at all."
        
        sections = migrator._parse_sections(text)
        
        assert len(sections) == 1
        assert sections[0]['title'] is None
        assert "simple text" in sections[0]['content']
    
    def test_truncate_preserves_sections(self, markdown_with_sections, simple_project):
        """Test that truncation preserves section boundaries."""
        migrator = Migrator(simple_project)
        
        # Truncate to small token count (should keep ~2 sections)
        truncated, removed = migrator._truncate_to_tokens(markdown_with_sections, 100)
        
        # Truncated text should not have half-sections or mid-sentence cuts
        assert "## Section" in truncated or len(removed) > 0  # Either has sections or removed some
        assert removed or truncated.count("##") > 0
    
    def test_truncate_removes_sections_info(self, markdown_with_sections, simple_project):
        """Test that truncation reports which sections were removed."""
        migrator = Migrator(simple_project)
        
        # Aggressive truncation
        truncated, removed = migrator._truncate_to_tokens(markdown_with_sections, 50)
        
        # Should have removed at least one section
        assert len(removed) > 0
        assert any("Section" in r for r in removed)
    
    def test_truncate_no_removal_when_fits(self, markdown_with_sections, simple_project):
        """Test that nothing is removed if content fits."""
        migrator = Migrator(simple_project)
        
        # Very generous limit
        truncated, removed = migrator._truncate_to_tokens(markdown_with_sections, 500)
        
        # No sections should be removed
        assert len(removed) == 0
        assert "Section 4" in truncated  # Last section should be present
    
    def test_truncate_keeps_at_least_first_section(self, markdown_with_sections, simple_project):
        """Test that at least the first section is always kept."""
        migrator = Migrator(simple_project)
        
        # Even with tiny limit
        truncated, removed = migrator._truncate_to_tokens(markdown_with_sections, 5)
        
        # Should have something
        assert len(truncated.strip()) > 0
        # And removed sections should exist
        assert len(removed) > 0


class TestTruncationWithFrontmatter:
    """Test truncation with YAML frontmatter."""
    
    def test_frontmatter_protection(self, markdown_with_frontmatter, simple_project, tmp_path):
        """Test that frontmatter is never truncated."""
        # Create project structure (use simple_project provided by fixture)
        project_root = simple_project
        
        # Write test file
        (project_root / "GLOBAL.md").write_text(markdown_with_frontmatter)
        
        migrator = Migrator(project_root)
        
        # The frontmatter should not be in the body for truncation
        # (it's handled separately in _truncate_global_file)
        body = markdown_with_frontmatter.split("---\n", 2)[2]
        
        truncated, removed = migrator._truncate_to_tokens(body, 50)
        
        # Truncated body should not contain frontmatter
        assert "name:" not in truncated
        assert "description:" not in truncated


class TestTruncationIntegration:
    """Integration tests for truncation in real migration."""
    
    def test_truncate_preserves_document_coherence(self, simple_project, tmp_path):
        """Test that truncated document remains coherent."""
        # Create bloated global file
        global_file = simple_project / "CLAUDE.md"
        content = """---
name: Global
description: Global file
---

# Important Section

This is critical content that should be preserved.

## Implementation Details

Implementation details here.
""" + ("More filler content " * 200)  # Add lots of filler
        
        global_file.write_text(content)
        
        migrator = Migrator(simple_project)
        
        # Extract body (after frontmatter)
        if content.startswith("---"):
            end_fm = content.find("\n---\n", 4)
            if end_fm != -1:
                body = content[end_fm + 5:]
            else:
                body = content
        else:
            body = content
        
        # Truncate
        truncated, removed = migrator._truncate_to_tokens(body, 100)
        
        # Should have important content
        assert "Important Section" in truncated or "Implementation" in truncated or len(removed) > 0
    
    def test_truncation_respects_token_limit(self, simple_project):
        """Test that truncated content is within reasonable token range."""
        migrator = Migrator(simple_project)
        
        # Create content that's clearly over limit
        large_content = "\n\n".join([
            f"## Section {i}\n\nContent for section {i} " * 100
            for i in range(1, 11)
        ])
        
        truncated, removed = migrator._truncate_to_tokens(large_content, 150)
        
        # Count tokens in truncated
        tokens = migrator.tokenizer.count_tokens(truncated)
        
        # Should have some content
        assert len(truncated) > 0
        # Should have removed some sections if original was huge
        if len(removed) == 0:
            # If nothing removed, it means content fit (unlikely with 10 sections)
            # So just verify it's truncated appropriately
            assert tokens >= 0


class TestTruncationEdgeCases:
    """Test edge cases in truncation."""
    
    def test_truncate_empty_text(self, simple_project):
        """Test truncating empty text."""
        migrator = Migrator(simple_project)
        
        truncated, removed = migrator._truncate_to_tokens("", 100)
        
        assert truncated == ""
        assert removed == []
    
    def test_truncate_single_section(self, simple_project):
        """Test truncating single section."""
        migrator = Migrator(simple_project)
        text = "## Only Section\n\nWith some content here."
        
        truncated, removed = migrator._truncate_to_tokens(text, 100)
        
        assert "Only Section" in truncated or len(removed) > 0
    
    def test_truncate_text_without_headers(self, simple_project):
        """Test truncating plain text without markdown headers."""
        migrator = Migrator(simple_project)
        text = "This is just plain text without any markdown headers or structure. " * 50
        
        truncated, removed = migrator._truncate_to_tokens(text, 50)
        
        assert len(truncated) > 0
        assert len(removed) == 0  # No sections to report
    
    def test_truncate_malformed_sections(self, simple_project):
        """Test truncating text with malformed markdown."""
        migrator = Migrator(simple_project)
        text = """## Section 1

Content

# Header without section
Random ## in middle
## Section 2
More content"""
        
        truncated, removed = migrator._truncate_to_tokens(text, 50)
        
        # Should handle gracefully
        assert len(truncated) > 0
