"""The number post-check (spec 13.1, P14): every number in the assistant's answer must appear in
this turn's tool outputs (or the question, or today's date), possibly written another way.

Numbers are compared in a canonical form, Turkish style: `.` groups thousands and `,` is the
decimal comma, so "1.349,90", "1349,90" and "1.349,9" are the same number, and "31.485,00" is
"31.485" is "31485". "01" is "1" (a day of an ISO date). A rounded, summed or invented number
("yaklaşık 1.350 TL") is not in the outputs and fails. Numbered list markers ("1. ", "2) ") at the
start of a line are not facts and are ignored.
"""

import re
from collections.abc import Iterable, Iterator
from typing import Any

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_LIST_MARKER = re.compile(r"^(\s*)\d{1,2}[.)]\s+", re.MULTILINE)
# Ids are not facts: the digits inside a UUID must not make an invented number "allowed".
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def canonical(number: str) -> str:
    integer, _, fraction = number.replace(".", "").partition(",")
    integer = integer.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    return f"{integer},{fraction}" if fraction else integer


def numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(text)


def strings_of(value: Any) -> Iterator[str]:
    """Every string and number inside a JSON-like value (keys too: they hold no facts, but a
    month key like '2026-11' is a fact)."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield _UUID.sub(" ", str(key))
            yield from strings_of(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_of(item)
    elif value is not None and not isinstance(value, bool):
        yield _UUID.sub(" ", str(value))


def allowed_numbers(sources: Iterable[Any]) -> set[str]:
    allowed: set[str] = set()
    for source in sources:
        for text in strings_of(source):
            allowed.update(canonical(n) for n in numbers_in(text))
    return allowed


def unsupported_numbers(answer: str, allowed: set[str]) -> list[str]:
    """The numbers of `answer` that are not in `allowed`, in order, without repeats."""
    text = _LIST_MARKER.sub(r"\1", answer)
    missing: list[str] = []
    for number in numbers_in(text):
        if canonical(number) not in allowed and number not in missing:
            missing.append(number)
    return missing


def correction_message(missing: list[str]) -> str:
    return (
        "Cevabındaki şu sayılar bu turdaki araç sonuçlarında yok: "
        + ", ".join(missing)
        + ". Sayı hesaplama, toplama ya da yuvarlama yapma. Cevabı yalnızca araç sonuçlarındaki "
        "sayıları aynen kullanarak yeniden yaz; gerekirse sayı vermeden anlat."
    )
