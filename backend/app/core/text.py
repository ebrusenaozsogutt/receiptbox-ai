"""Turkish-aware text helpers.

Only step 1 of spec section 5.6 lives here (uppercase, strip punctuation, collapse spaces).
Removing legal suffixes, fuzzy matching and merchant creation are P06.
"""

import re
import unicodedata

# Dots and apostrophes are removed without a space: "A.Ş." -> "AŞ", "McDonald's" -> "MCDONALDS".
_JOINING_PUNCTUATION = re.compile(r"[.'’‘`´]")
# Any other character that is not a letter, digit or space becomes a space ("MIGROS-TICARET").
_OTHER_PUNCTUATION = re.compile(r"[^\w\s]|_", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def turkish_upper(text: str) -> str:
    """Uppercase with Turkish rules: i -> İ and ı -> I (Python's default maps i -> I)."""
    return text.replace("i", "İ").replace("ı", "I").upper()


def normalize_alias_key(text: str) -> str:
    """Normalise a merchant name for alias lookup (spec 5.6, step 1)."""
    text = unicodedata.normalize("NFC", text)
    text = turkish_upper(text)
    text = _JOINING_PUNCTUATION.sub("", text)
    text = _OTHER_PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()
