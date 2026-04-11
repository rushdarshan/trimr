import logging
from typing import Optional

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

logger = logging.getLogger(__name__)


class Tokenizer:
    """Token counter using tiktoken with word-count fallback."""

    def __init__(self):
        self.encoder = None
        if HAS_TIKTOKEN:
            try:
                self.encoder = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"[WARN] Failed to load tiktoken encoding: {e}. Using word-count fallback.")
                self.encoder = None
        else:
            logger.warning("[WARN] tiktoken not installed. Using word-count fallback.")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text. Falls back to word-count approximation if tiktoken unavailable."""
        if self.encoder is not None:
            try:
                return len(self.encoder.encode(text))
            except Exception as e:
                logger.warning(f"[WARN] Tokenization failed: {e}. Using word-count fallback.")
                return self._word_count_approximation(text)
        else:
            return self._word_count_approximation(text)

    @staticmethod
    def _word_count_approximation(text: str) -> int:
        """Approximate token count using word count (rough 1.3x multiplier for cl100k_base)."""
        word_count = len(text.split())
        return max(1, int(word_count * 1.3))


_default_tokenizer: Optional[Tokenizer] = None


def get_tokenizer() -> Tokenizer:
    """Get or create singleton tokenizer instance."""
    global _default_tokenizer
    if _default_tokenizer is None:
        _default_tokenizer = Tokenizer()
    return _default_tokenizer
