import pytest
from trimr.tokenizer import Tokenizer, get_tokenizer


def test_tokenizer_initialization():
    """Test tokenizer initializes without error."""
    tokenizer = Tokenizer()
    assert tokenizer is not None


def test_tokenizer_count_tokens_basic():
    """Test basic token counting."""
    tokenizer = Tokenizer()
    result = tokenizer.count_tokens("hello world")
    assert result > 0
    assert isinstance(result, int)


def test_tokenizer_count_tokens_empty():
    """Test token counting for empty string."""
    tokenizer = Tokenizer()
    result = tokenizer.count_tokens("")
    assert result >= 0


def test_tokenizer_word_count_approximation():
    """Test word count approximation fallback."""
    result = Tokenizer._word_count_approximation("hello world test example")
    assert result > 0
    assert isinstance(result, int)


def test_tokenizer_word_count_approximation_single_word():
    """Test word count with single word."""
    result = Tokenizer._word_count_approximation("hello")
    assert result >= 1


def test_tokenizer_word_count_approximation_empty():
    """Test word count with empty string."""
    result = Tokenizer._word_count_approximation("")
    assert result >= 1


def test_singleton_tokenizer():
    """Test that get_tokenizer returns same instance."""
    t1 = get_tokenizer()
    t2 = get_tokenizer()
    assert t1 is t2


def test_tokenizer_longer_text():
    """Test token counting with longer text."""
    text = "The quick brown fox jumps over the lazy dog. " * 10
    tokenizer = Tokenizer()
    result = tokenizer.count_tokens(text)
    assert result > 0
