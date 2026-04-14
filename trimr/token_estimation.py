"""Token estimation utilities for accurate projections."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def estimate_pointer_tokens(skill_name: str, skill_description: str) -> int:
    """
    Estimate tokens for a pointer file (skill in vault).
    
    Generates the actual YAML pointer that would be created and counts tokens.
    This gives accurate L1 metadata cost instead of arbitrary 100-token guess.
    
    Args:
        skill_name: Name of the skill
        skill_description: Description of the skill
    
    Returns:
        Estimated token count for pointer file
    """
    from .tokenizer import get_tokenizer
    
    try:
        tokenizer = get_tokenizer()
    except Exception as e:
        logger.warning(f"Failed to load tokenizer for estimation: {e}. Using conservative estimate.")
        return _estimate_pointer_tokens_fallback(skill_name, skill_description)
    
    # Generate the actual pointer YAML
    pointer_content = _generate_pointer_yaml(skill_name, skill_description)
    
    # Count real tokens
    try:
        tokens = tokenizer.count_tokens(pointer_content)
        logger.debug(f"Estimated {tokens} tokens for pointer: {skill_name}")
        return tokens
    except Exception as e:
        logger.warning(f"Failed to estimate tokens for {skill_name}: {e}. Using fallback.")
        return _estimate_pointer_tokens_fallback(skill_name, skill_description)


def _generate_pointer_yaml(skill_name: str, skill_description: str) -> str:
    """Generate the actual pointer YAML that would be in the global file."""
    # This mirrors what migrator.py creates
    pointer = f"""---
name: "{skill_name}"
description: "{skill_description}"
---

This skill is in vault. Use load_skill(...) to access it.
"""
    return pointer.strip()


def _estimate_pointer_tokens_fallback(skill_name: str, skill_description: str) -> int:
    """
    Conservative fallback estimation when tokenizer unavailable.
    
    Uses heuristic: ~1 token per 4 characters (conservative).
    """
    content_length = len(skill_name) + len(skill_description)
    # Conservative: ~1 token per 4 chars, plus YAML overhead (~20 tokens)
    estimated = (content_length // 4) + 20
    
    # Reasonable range: 10-50 tokens for most skills
    estimated = max(10, min(50, estimated))
    
    logger.debug(f"Using fallback estimation: {estimated} tokens for {skill_name}")
    return estimated


def estimate_skill_pointer_tokens(skill_name: str, skill_description: str, tokenizer=None) -> int:
    """
    Estimate tokens for a skill pointer (for projection calculation).
    
    This is the primary function for calculating projected costs.
    Uses real token counting when possible, falls back to conservative estimate.
    
    Args:
        skill_name: Skill name from frontmatter
        skill_description: Skill description from frontmatter
        tokenizer: Optional pre-loaded tokenizer (to avoid reloading)
    
    Returns:
        Token count for this skill's L1 metadata pointer
    """
    if not skill_name or not skill_description:
        # Invalid skill, use minimal estimate
        return 10
    
    try:
        # Try to use provided tokenizer if available
        if tokenizer:
            pointer = _generate_pointer_yaml(skill_name, skill_description)
            tokens = tokenizer.count_tokens(pointer)
            logger.debug(f"Estimated {tokens} tokens for skill pointer: {skill_name}")
            return max(10, tokens)  # Minimum 10 tokens
        else:
            # Fall back to function that loads tokenizer
            return estimate_pointer_tokens(skill_name, skill_description)
    except Exception as e:
        logger.warning(f"Token estimation failed for {skill_name}: {e}")
        return _estimate_pointer_tokens_fallback(skill_name, skill_description)
