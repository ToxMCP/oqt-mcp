"""Sanitization utilities for trust-boundary safety."""

import re
import unicodedata


def sanitize_for_llm(text: str | None) -> str:
    """
    Sanitize untrusted text before it crosses into an LLM prompt or agent context.

    Controls applied:
    - Normalize Unicode to NFKC
    - Strip control and zero-width characters
    - Collapse multiple newlines
    - Remove backticks and dollar signs that could be interpreted as formatting
    """
    if not text:
        return ""

    # Normalize Unicode
    normalized = unicodedata.normalize("NFKC", text)

    # Remove zero-width and control characters (keep basic whitespace)
    cleaned_chars = []
    for char in normalized:
        cat = unicodedata.category(char)
        if cat.startswith("C") and char not in "\n\t\r":
            continue
        cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars)

    # Remove formatting-sensitive characters
    cleaned = cleaned.replace("`", "").replace("$", "")

    # Collapse excessive newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()
