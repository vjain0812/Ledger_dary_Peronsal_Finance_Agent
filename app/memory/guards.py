"""Write-side and read-side guards for long-term memory.

These are a first line of defence only. For real PII coverage, put a detector such as
Microsoft Presidio behind `find_sensitive` and keep the same interface.
"""

import re

# long digit runs, card-like numbers (13-19 digits, optional separators), US SSN format
_NUMBERS = re.compile(r"\b\d{9,}\b|\b(?:\d[ -]?){13,19}\b|\b\d{3}-\d{2}-\d{4}\b")
_SECRETS = re.compile(r"\b(?:password|passcode|passwd|cvv|cvc|pin)\b\s*(?:is|=|:)", re.I)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def find_sensitive(text: str) -> str | None:
    """Return a short reason if the text looks like it contains sensitive data."""
    if _NUMBERS.search(text):
        return "looks like it contains a sensitive account or ID number"
    if _SECRETS.search(text):
        return "looks like it contains a password or security code"
    return None


def sanitize_for_prompt(text: str, max_chars: int = 300) -> str:
    """Make stored text safe(ish) to place back into a prompt: single line, no tags, capped."""
    text = _CONTROL.sub(" ", str(text))
    text = text.replace("<", "").replace(">", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def validate_memory_content(content: str, max_chars: int = 300) -> str | None:
    """Return an error message if the content must not be stored, else None."""
    if not content or not content.strip():
        return "content is empty"
    if len(content) > max_chars:
        return f"content is longer than {max_chars} characters"
    return find_sensitive(content)
