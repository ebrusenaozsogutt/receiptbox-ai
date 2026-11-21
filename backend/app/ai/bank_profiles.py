"""What differs between banks, as data (P08, DECISIONS D-013).

Three banks are fully supported (prompt hints in `prompts/banks/<bank>.md` and fixtures): Garanti
BBVA (also its Bonus cards), Kuveyt Türk and Akbank. QNB and Ziraat are deliberately NOT here: they
are the "unseen bank" set that measures how well the general prompt generalises, so their screens
are read without any bank-specific help (`bank_key` is stored as null).
"""

from dataclasses import dataclass

SUPPORTED_BANKS = ("garanti", "kuveyt", "akbank")


@dataclass(frozen=True)
class BankProfile:
    key: str | None
    # Most apps print money that came back with a "+" and a purchase with "-" or no sign. Akbank
    # prints a purchase without a sign and a payment or credit with "-".
    minus_is_credit: bool = False


GENERIC = BankProfile(key=None)

_PROFILES = {
    "garanti": BankProfile("garanti"),
    "kuveyt": BankProfile("kuveyt"),
    "akbank": BankProfile("akbank", minus_is_credit=True),
}


def normalize_bank_hint(hint: str | None) -> str | None:
    """The key of a supported bank, or None (no hint, an unknown bank, or one of the held-out
    banks). Never raises: a wrong hint only means no bank-specific help."""
    if hint is None:
        return None
    key = hint.strip().lower()
    return key if key in SUPPORTED_BANKS else None


def profile_for(bank_key: str | None) -> BankProfile:
    return _PROFILES.get(bank_key or "", GENERIC)
