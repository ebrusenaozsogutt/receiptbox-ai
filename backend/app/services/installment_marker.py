"""Finds an installment marker in a bank row's text (spec 5.5, P08) and says which part it is.

Examples that are recognised (the letters are compared without Turkish diacritics and in capitals):

    2/6          (2/6)         2/6 TAKSİT       TAKSİT 2/6        Taksit: 01/03
    (01/03)      2/4 Taksidi   3 TAKSİTLİ       6 TAKSİT          TAKSİT SAYISI: 3
    02.Tak       2. taksit     O1/03 (OCR: letter O for zero)

`seq` is k in "k/n" and `count` is n; a text that only says "3 TAKSİTLİ" gives count 3 and no seq.
Only the marker is stored here (logic, plans and matching are P10).

A date such as "20/10" in front of a merchant name is not a marker: the plain `k/n` form is only
accepted in parentheses, next to the word "taksit", or at the very end of the text, and `k` can
not be bigger than `n`.
"""

import re
from dataclasses import dataclass

from app.core.text import turkish_upper

MAX_INSTALLMENTS = 60  # the same limit as the receipt validation

_ASCII = str.maketrans("İŞĞÜÖÇ", "ISGUOC")


@dataclass(frozen=True)
class InstallmentMarker:
    seq: int | None
    count: int | None
    # The pieces of the original text that were the marker (to cut them out of a merchant name).
    spans: tuple[tuple[int, int], ...] = ()


def _fold(text: str) -> str:
    folded = turkish_upper(text).translate(_ASCII)
    return folded if len(folded) == len(text) else text.upper()


_N = r"([0-9OIL]{1,2})"  # a number; OCR may read O for 0 and I or L for 1
_TAKSIT = r"TAKS[I1]D?[I1]?T?(?:L[I1])?"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # TAKSİT: 01/03   TAKSİT 2/6
    (re.compile(rf"TAKS[I1]T\s*:?\s*{_N}\s*/\s*{_N}"), "seq_count"),
    # 2/6 TAKSİT   2/4 TAKSİDİ
    (re.compile(rf"(?<![0-9/]){_N}\s*/\s*{_N}\s*TAKS[I1]\w*"), "seq_count"),
    # the whole text is just the marker: "2/6"
    (re.compile(rf"^\s*{_N}\s*/\s*{_N}\s*$"), "seq_count"),
    # (2/6)
    (re.compile(rf"\(\s*{_N}\s*/\s*{_N}\s*\)"), "seq_count"),
    # TAKSİT SAYISI: 3
    (re.compile(r"TAKS[I1]T\s*SAY[I1]S[I1]\s*:?\s*([0-9OIL]{1,2})"), "count"),
    # 3 TAKSİTLİ   6 TAKSİT
    (re.compile(rf"(?<![0-9/.,])(?<!/ ){_N}\s*{_TAKSIT}\b"), "count"),
    # 2. TAKSİT
    (re.compile(rf"(?<![0-9/.,]){_N}\s*\.\s*TAKS[I1]T"), "seq"),
    # 02.Tak
    (re.compile(rf"(?<![0-9/.,]){_N}\s*\.\s*TAK\b"), "seq"),
    # a plain k/n at the very end (not at the start: that is a date)
    (re.compile(rf"(?<=[^\s0-9/])\s+{_N}\s*/\s*{_N}\s*$"), "seq_count"),
)


def _number(text: str) -> int:
    if not re.search(r"\d", text):  # only letters (OCR look-alikes): not a number
        raise ValueError("no digit")
    return int(text.replace("O", "0").replace("I", "1").replace("L", "1"))


def parse_installment_marker(text: str | None) -> InstallmentMarker | None:
    """The marker in [text], or None. Never raises."""
    if not text or not text.strip():
        return None
    folded = _fold(text)
    seq: int | None = None
    count: int | None = None
    spans: list[tuple[int, int]] = []

    for pattern, kind in _PATTERNS:
        for match in pattern.finditer(folded):
            try:
                if kind == "seq_count":
                    k, n = _number(match[1]), _number(match[2])
                    if not (2 <= n <= MAX_INSTALLMENTS and 1 <= k <= n):
                        continue
                    seq, count = (seq or k), (count or n)
                elif kind == "count":
                    n = _number(match[1])
                    if not 2 <= n <= MAX_INSTALLMENTS:
                        continue
                    count = count or n
                else:
                    k = _number(match[1])
                    if not 1 <= k <= MAX_INSTALLMENTS:
                        continue
                    seq = seq or k
            except ValueError:
                continue
            spans.append(match.span())
    if seq is None and count is None:
        return None
    if seq is not None and count is not None and seq > count:
        return None  # contradicting pieces: better no marker than a wrong one
    return InstallmentMarker(seq=seq, count=count, spans=tuple(spans))


def strip_marker(text: str, marker: InstallmentMarker | None) -> str:
    """[text] without the marker (for the merchant name), with tidy spaces."""
    if marker is None or not marker.spans:
        return text
    pieces: list[str] = []
    position = 0
    for start, end in sorted(set(marker.spans)):
        if start < position:
            continue
        pieces.append(text[position:start])
        position = end
    pieces.append(text[position:])
    cleaned = re.sub(r"\(\s*\)", " ", "".join(pieces))
    return re.sub(r"\s+", " ", cleaned).strip(" -:,/")
