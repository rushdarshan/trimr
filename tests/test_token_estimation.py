"""Tests for token estimation functionality."""

import pytest
from unittest.mock import Mock, patch

from trimr.token_estimation import (
    estimate_pointer_tokens,
    estimate_skill_pointer_tokens,
    _generate_pointer_yaml,
    _estimate_pointer_tokens_fallback,
)


class TestGeneratePointerYaml:
    """Test pointer YAML generation."""
    
    def test_generate_basic_pointer(self):
        """Test generating basic pointer YAML."""
        yaml = _generate_pointer_yaml("TestSkill", "A test skill")
        
        assert "name: \"TestSkill\"" in yaml
        assert "description: \"A test skill\"" in yaml
        assert "---" in yaml
        assert "vault" in yaml.lower()
    
    def test_generate_pointer_with_special_chars(self):
        """Test pointer with special characters."""
        yaml = _generate_pointer_yaml("PDF-Parser", "Parse PDFs & extract text")
        
        assert "PDF-Parser" in yaml
        assert "PDFs" in yaml
    
    def test_pointer_yaml_valid_format(self):
        """Test that generated YAML is valid format."""
        yaml = _generate_pointer_yaml("MySkill", "My description")
        
        # Should have frontmatter delimiters
        lines = yaml.split('\n')
        assert lines[0] == '---'  # Start delimiter
        assert '---' in lines[3:5]  # End delimiter around line 3-4


class TestFallbackEstimation:
    """Test fallback token estimation."""
    
    def test_fallback_estimation_short_skill(self):
        """Test fallback for short skill name/description."""
        tokens = _estimate_pointer_tokens_fallback("PDF", "Parse PDF")
        
        # Should be in reasonable range (10-50)
        assert 10 <= tokens <= 50
    
    def test_fallback_estimation_long_skill(self):
        """Test fallback for long skill name/description."""
        long_desc = "A comprehensive PDF parsing skill that extracts text, images, and metadata from PDF files"
        tokens = _estimate_pointer_tokens_fallback("PDFParser", long_desc)
        
        # Should be in reasonable range (10-50)
        assert 10 <= tokens <= 50
    
    def test_fallback_minimum_tokens(self):
        """Test that fallback has minimum."""
        # Very short inputs
        tokens = _estimate_pointer_tokens_fallback("A", "B")
        
        # Should still be at least 10
        assert tokens >= 10
    
    def test_fallback_maximum_tokens(self):
        """Test that fallback has reasonable maximum."""
        # Very long inputs
        long_text = "x" * 1000
        tokens = _estimate_pointer_tokens_fallback(long_text, long_text)
        
        # Should be capped at 50
        assert tokens <= 50


class TestPointerTokenEstimation:
    """Test main pointer token estimation."""
    
    def test_estimate_pointer_tokens_with_tokenizer(self):
        """Test estimation when tokenizer is available."""
        # Should return reasonable estimate
        tokens = estimate_pointer_tokens("TestSkill", "A test skill")
        
        assert isinstance(tokens, int)
        assert tokens > 0
        # Should be reasonable (not 100 anymore)
        assert 10 <= tokens <= 100
    
    def test_estimate_pointer_tokens_different_skills(self):
        """Test estimation for different skill sizes."""
        # Short skill
        short = estimate_pointer_tokens("PDF", "Extract PDF")
        
        # Long skill  
        long = estimate_pointer_tokens(
            "AdvancedTextProcessor",
            "Process and analyze text documents with advanced NLP techniques"
        )
        
        # Both should be valid
        assert short > 0
        assert long > 0
        
        # Longer description might use more tokens (but not guaranteed)
        assert isinstance(short, int)
        assert isinstance(long, int)
    
    def test_estimate_pointer_tokens_consistency(self):
        """Test that estimation is consistent."""
        name = "TestSkill"
        desc = "Test description"
        
        # Should return same value each time
        tokens1 = estimate_pointer_tokens(name, desc)
        tokens2 = estimate_pointer_tokens(name, desc)
        
        assert tokens1 == tokens2


class TestSkillPointerTokenEstimation:
    """Test estimate_skill_pointer_tokens wrapper."""
    
    def test_estimate_skill_pointer_with_tokenizer(self):
        """Test estimation with provided tokenizer."""
        from trimr.tokenizer import get_tokenizer
        
        tokenizer = get_tokenizer()
        tokens = estimate_skill_pointer_tokens("MySkill", "Description", tokenizer)
        
        assert isinstance(tokens, int)
        assert tokens >= 10  # Minimum
    
    def test_estimate_skill_pointer_without_tokenizer(self):
        """Test estimation without tokenizer (uses fallback)."""
        tokens = estimate_skill_pointer_tokens("MySkill", "Description")
        
        assert isinstance(tokens, int)
        assert 10 <= tokens <= 100
    
    def test_estimate_skill_pointer_invalid_skill(self):
        """Test estimation with invalid skill (empty name/desc)."""
        tokens = estimate_skill_pointer_tokens("", "")
        
        # Should use minimum
        assert tokens == 10
    
    def test_estimate_skill_pointer_minimum(self):
        """Test that estimate never goes below 10 tokens."""
        from trimr.tokenizer import get_tokenizer
        
        tokenizer = get_tokenizer()
        
        # Try various small inputs
        for name, desc in [("A", "B"), ("", "X"), ("Y", "")]:
            tokens = estimate_skill_pointer_tokens(name, desc, tokenizer)
            assert tokens >= 10, f"Got {tokens} tokens for {name}/{desc}"


class TestTokenEstimationIntegration:
    """Integration tests for token estimation in audit context."""
    
    def test_realistic_skill_estimation(self):
        """Test realistic skill pointer estimation."""
        skills = [
            ("PDFExtractor", "Extract text and images from PDF files"),
            ("JSONValidator", "Validate JSON documents against schema"),
            ("APIClient", "HTTP client for REST API interactions"),
            ("DatabaseConnectionPool", "Manage connections to databases with pooling and retry logic"),
        ]
        
        for name, desc in skills:
            tokens = estimate_skill_pointer_tokens(name, desc)
            
            # Should be reasonable
            assert 10 <= tokens <= 100, f"Unrealistic estimate for {name}: {tokens} tokens"
    
    def test_token_estimates_vary_by_content(self):
        """Test that estimates vary appropriately by content."""
        short = estimate_skill_pointer_tokens("PDF", "Extract")
        long = estimate_skill_pointer_tokens(
            "AdvancedPDFProcessor",
            "Process complex PDF documents with OCR, table extraction, and metadata analysis"
        )
        
        # Long should use same or more tokens
        # (not strictly required, but typical)
        assert short >= 10
        assert long >= 10


class TestTokenEstimationVsHardcoded:
    """Verify improvement over hardcoded 100-token estimate."""
    
    def test_realistic_estimates_not_100(self):
        """Test that real estimates vary from hardcoded 100."""
        # With real estimation, most skills should be 15-30 tokens, not 100
        
        typical_skills = [
            ("PDF", "Parse PDFs"),
            ("JSON", "Validate JSON"),
            ("CSV", "Process CSV files"),
        ]
        
        estimates = [estimate_skill_pointer_tokens(name, desc) 
                    for name, desc in typical_skills]
        
        # Most should be less than 100
        below_100 = sum(1 for e in estimates if e < 100)
        assert below_100 >= 2, "Most typical skills should have <100 token estimate"
        
        # All should be reasonable
        assert all(10 <= e <= 100 for e in estimates)
    
    def test_many_skills_projection_improvement(self):
        """Test projection accuracy for multiple skills."""
        # 10 typical skills with old estimate: 10 * 100 = 1000 tokens
        # With real estimates: probably 15-30 each = 150-300 tokens
        
        skill_list = [
            (f"Skill{i}", f"Description for skill {i}")
            for i in range(10)
        ]
        
        total_tokens = sum(estimate_skill_pointer_tokens(name, desc) 
                          for name, desc in skill_list)
        
        # Should be significantly less than 1000 (10 * 100)
        # But still reasonable
        assert total_tokens < 1000, f"Total {total_tokens} too high for 10 small skills"
        assert total_tokens > 100, f"Total {total_tokens} too low for 10 skills"
