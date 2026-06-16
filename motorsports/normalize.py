"""Text normalization for fuzzy matching."""

import re

from unidecode import unidecode


def normalize_text(value: str) -> str:
    """Normalize text for fuzzy matching.

    Strips accents, lowercases, removes punctuation, normalizes whitespace.
    """
    normalized = unidecode(value).lower().strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized
