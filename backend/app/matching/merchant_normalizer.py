"""Merchant normalisation, spec 5.6.

Pure functions (cleaning, scoring, titles) are at the top and need no database. `MerchantNormalizer`
at the bottom adds the repository calls: alias lookup (the user's own aliases first, then the
global ones) and fuzzy matching against the canonical names.

Steps of spec 5.6 and where they are:
  1. Turkish-aware upper case, punctuation removed, spaces collapsed  -> `clean_name`
  2. legal and branch suffixes, trailing store codes and city names    -> `clean_name`
  3. alias lookup, user before global                                   -> `MerchantNormalizer`
  4. fuzzy match, rapidfuzz `token_set_ratio >= 90`                     -> `MerchantNormalizer`
  5. otherwise a NEW merchant: only a proposed name is returned here; the row is created by
     `MerchantRepository.create` when the user confirms (P07), see DECISIONS.

Deviations from the spec text (recorded in DECISIONS): the suffix list is longer; city names are
only removed at the END of the name ("ADANA KEBAP" stays); and a fuzzy match must also pass a
`token_sort_ratio >= 75` check and the name must have at least 5 letters, because
`token_set_ratio` is 100 whenever one name's words are a subset of the other's ("KAHVE" would
match "Kahve Dünyası").
"""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from rapidfuzz import fuzz, process

from app.core.text import normalize_alias_key, turkish_upper
from app.models.enums import CategoryKey
from app.repositories.merchants import MerchantInfo, MerchantRepository

FUZZY_MIN_SCORE = 90
FUZZY_MIN_SORT_SCORE = 75
FUZZY_MIN_LENGTH = 5

_ASCII = str.maketrans("İŞĞÜÖÇ", "ISGUOC")

# Single words that are legal form or branch noise (ASCII, upper case). Spec 5.6 step 2 plus a few
# that real receipts print (TICARET, SANAYI, LIMITED, ISTASYONU ...).
LEGAL_TOKENS = frozenset(
    {
        "AS", "TIC", "TICARET", "LTD", "LIMITED", "STI", "SIRKETI", "SAN", "SANAYI", "ANONIM",
        "MAGAZACILIK", "GIDA", "PAZARLAMA", "SUBE", "SUBESI", "ISTASYONU", "ISTASYON",
        "HIZMETLERI", "ELEKTRONIK",
    }
)  # fmt: skip
# Word groups removed as a whole.
LEGAL_PHRASES = (("SANAL", "MARKET"), ("IC", "VE", "DIS"), ("A", "S"), ("SANAYI", "VE"))
# Words that introduce a store number: "NO 1234", "KASA 02".
_STORE_MARKERS = frozenset({"NO", "NUMARA", "MNO", "KASA", "M"})

CITIES = frozenset(
    """ADANA ADIYAMAN AFYONKARAHISAR AGRI AKSARAY AMASYA ANKARA ANTALYA ARDAHAN ARTVIN AYDIN
    BALIKESIR BARTIN BATMAN BAYBURT BILECIK BINGOL BITLIS BOLU BURDUR BURSA CANAKKALE CANKIRI
    CORUM DENIZLI DIYARBAKIR DUZCE EDIRNE ELAZIG ERZINCAN ERZURUM ESKISEHIR GAZIANTEP GIRESUN
    GUMUSHANE HAKKARI HATAY IGDIR ISPARTA ISTANBUL IZMIR KAHRAMANMARAS KARABUK KARAMAN KARS
    KASTAMONU KAYSERI KILIS KIRIKKALE KIRKLARELI KIRSEHIR KOCAELI KONYA KUTAHYA MALATYA MANISA
    MARDIN MERSIN MUGLA MUS NEVSEHIR NIGDE ORDU OSMANIYE RIZE SAKARYA SAMSUN SANLIURFA SIIRT SINOP
    SIVAS SIRNAK TEKIRDAG TOKAT TRABZON TUNCELI USAK VAN YALOVA YOZGAT ZONGULDAK""".split()
)


def fold_ascii(text: str) -> str:
    """Upper-case Turkish letters to plain ASCII: "MİĞROŞ" -> "MIGROS"."""
    return turkish_upper(text).translate(_ASCII)


@dataclass(frozen=True)
class CleanedName:
    full: str  # step 1 only, Turkish upper case ("MİGROS TİCARET AŞ")
    stripped: str  # after step 2 ("MİGROS")

    @property
    def lookup_keys(self) -> list[str]:
        """Alias keys to try, most specific first. The database holds each alias in its Turkish
        form and in its ASCII form (receipts are often printed without Turkish letters)."""
        keys = [self.full, fold_ascii(self.full), self.stripped, fold_ascii(self.stripped)]
        return list(dict.fromkeys(key for key in keys if key))


def clean_name(raw: str) -> CleanedName:
    """Steps 1 and 2 of spec 5.6."""
    full = normalize_alias_key(raw)
    tokens = full.split()
    if not tokens:
        return CleanedName(full="", stripped="")

    kept = _remove_legal_words(tokens)
    kept = [_without_domain_ending(token) for token in kept]
    kept = _remove_trailing_codes_and_cities(kept)
    return CleanedName(full=full, stripped=" ".join(kept) if kept else full)


def _without_domain_ending(token: str) -> str:
    """ "TRENDYOLCOM" (from "TRENDYOL.COM") -> "TRENDYOL"; the dot was removed in step 1."""
    for ending in ("COMTR", "COM"):
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def _remove_legal_words(tokens: list[str]) -> list[str]:
    folded = [fold_ascii(token) for token in tokens]
    remove = [False] * len(tokens)
    for phrase in LEGAL_PHRASES:
        size = len(phrase)
        for start in range(len(tokens) - size + 1):
            if tuple(folded[start : start + size]) == phrase:
                # Never remove everything: "SANAL MARKET" alone is a name, not a suffix.
                if size < len(tokens):
                    remove[start : start + size] = [True] * size
    for index, token in enumerate(folded):
        if token in LEGAL_TOKENS:
            remove[index] = True
    kept = [token for token, drop in zip(tokens, remove, strict=True) if not drop]
    while kept and fold_ascii(kept[-1]) == "VE":  # "SANAYI VE TICARET" leaves a dangling "VE"
        kept.pop()
    return kept or tokens


def _remove_trailing_codes_and_cities(tokens: list[str]) -> list[str]:
    kept = list(tokens)
    while len(kept) > 1:
        last = fold_ascii(kept[-1])
        if last.isdigit() or last in CITIES or last in _STORE_MARKERS:
            kept.pop()
        else:
            break
    return kept


def turkish_title(text: str) -> str:
    """ "KOSE MANAV" -> "Kose Manav". Short words and words with digits stay upper case (A101)."""
    words = []
    for word in text.split():
        if len(word) <= 3 or any(char.isdigit() for char in word):
            words.append(word)
            continue
        first, rest = word[0], word[1:]
        # A word with a Turkish letter (İ Ş Ğ Ü Ö Ç) was written with Turkish letters: I is then
        # a dotless ı. In ASCII-only receipt text ("KUCUKYALI") I stands for either; i is likelier.
        dotless = "ı" if any(char in word for char in "İŞĞÜÖÇ") else "i"
        lowered = rest.replace("İ", "i").replace("I", dotless).lower()
        words.append(turkish_upper(first) + lowered)
    return " ".join(words)


def fuzzy_pick(query: str, choices: list[str]) -> tuple[int, float] | None:
    """The index and score of the best canonical name, or None. Pure."""
    if len(query.replace(" ", "")) < FUZZY_MIN_LENGTH or not choices:
        return None
    best = process.extractOne(
        query, choices, scorer=fuzz.token_set_ratio, score_cutoff=FUZZY_MIN_SCORE
    )
    if best is None:
        return None
    _, score, index = best
    if fuzz.token_sort_ratio(query, choices[index]) < FUZZY_MIN_SORT_SCORE:
        return None
    return index, float(score)


# ---- with the database -----------------------------------------------------------------------

MatchKind = Literal["USER_ALIAS", "GLOBAL_ALIAS", "FUZZY", "NEW", "NONE"]


@dataclass(frozen=True)
class MerchantMatch:
    kind: MatchKind
    merchant_id: uuid.UUID | None = None
    canonical_name: str | None = None
    default_category: CategoryKey | None = None
    score: float | None = None
    alias_keys: list[str] = field(default_factory=list)  # for creating a NEW merchant later


def vkn_alias_key(seller_id: str) -> str:
    """How a seller's tax number is stored as an alias ("VKN 1234567890")."""
    return f"VKN {seller_id}"


class MerchantNormalizer:
    def __init__(self, repository: MerchantRepository) -> None:
        self._repository = repository

    async def resolve(
        self, user_id: uuid.UUID, raw_name: str | None, *, seller_id: str | None = None
    ) -> MerchantMatch:
        # A seller's tax number the user (or the seed) has named before is the surest signal.
        if seller_id:
            hit = await self._alias_match(user_id, [vkn_alias_key(seller_id)])
            if hit is not None:
                return hit

        if raw_name is None or not raw_name.strip():
            return MerchantMatch(kind="NONE")
        cleaned = clean_name(raw_name)
        if not cleaned.full:
            return MerchantMatch(kind="NONE")

        hit = await self._alias_match(user_id, cleaned.lookup_keys)
        if hit is not None:
            return hit

        fuzzy = await self._fuzzy_match(user_id, cleaned)
        if fuzzy is not None:
            return fuzzy

        return MerchantMatch(
            kind="NEW",
            canonical_name=turkish_title(cleaned.stripped),
            alias_keys=cleaned.lookup_keys,
        )

    async def _alias_match(self, user_id: uuid.UUID, keys: list[str]) -> MerchantMatch | None:
        hits = await self._repository.find_aliases(user_id, keys)
        if not hits:
            return None
        # The user's own alias beats a global one; inside one scope the more specific key wins.
        order = {key: position for position, key in enumerate(keys)}
        best = min(hits, key=lambda hit: (not hit.is_user_alias, order[hit.alias_normalized]))
        return MerchantMatch(
            kind="USER_ALIAS" if best.is_user_alias else "GLOBAL_ALIAS",
            merchant_id=best.merchant.id,
            canonical_name=best.merchant.canonical_name,
            default_category=best.merchant.default_category,
        )

    async def _fuzzy_match(self, user_id: uuid.UUID, cleaned: CleanedName) -> MerchantMatch | None:
        merchants = await self._repository.list_merchants(user_id)
        choices = [
            fold_ascii(normalize_alias_key(merchant.canonical_name)) for merchant in merchants
        ]
        picked = fuzzy_pick(fold_ascii(cleaned.stripped), choices)
        if picked is None:
            return None
        index, score = picked
        merchant = merchants[index]
        return MerchantMatch(
            kind="FUZZY",
            merchant_id=merchant.id,
            canonical_name=merchant.canonical_name,
            default_category=merchant.default_category,
            score=score,
        )


__all__ = [
    "CleanedName",
    "MerchantInfo",
    "MerchantMatch",
    "MerchantNormalizer",
    "clean_name",
    "fold_ascii",
    "fuzzy_pick",
    "turkish_title",
    "vkn_alias_key",
]
