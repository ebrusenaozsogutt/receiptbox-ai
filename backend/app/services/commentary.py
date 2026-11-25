"""The optional AI commentary on a spending comparison (spec 11.2, P11).

Privacy and correctness rules, each enforced here (and tested):
- The model receives ONLY the computed aggregates of `CompareOut`: two period totals, the
  difference, the change in percent and up to three categories with their two amounts. Never a
  transaction, a shop, an item, a date of a purchase or a user id (`build_facts`).
- The LLM never produces a number shown as a fact: every number in the answer must be one of the
  numbers written in the facts, character for character, or the answer is dropped
  (`accept_answer`). At most two sentences are kept.
- No consent, no provider, a provider error or a rejected answer -> no commentary (null). The
  screen then simply shows nothing.
- Answers are cached per user and per facts text (which contains the two periods), so the same
  comparison does not call the model again; the cache lives in the process (no Redis, D-008).
"""

import hashlib
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import date

from app.ai.provider import AIProvider, ProviderError
from app.core.money import format_minor
from app.schemas.analytics import CompareOut

logger = logging.getLogger("receiptbox.commentary")

MAX_SENTENCES = 2
MAX_CHARS = 320
CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_SIZE = 1000

_MONTHS_TR = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def money(minor: int) -> str:
    return f"{format_minor(minor)} TL"


def percent(value: float) -> str:
    return "%" + f"{value:.1f}".replace(".", ",")


def _day(d: date) -> str:
    return f"{d.day} {_MONTHS_TR[d.month - 1]} {d.year}"


def build_facts(result: CompareOut) -> str:
    """The whole input of the model: computed numbers and category names, nothing else."""
    lines = [
        f"Dönem A: {_day(result.a.date_from)} - {_day(result.a.date_to)}, "
        f"toplam harcama {money(result.a.total_minor)}",
        f"Dönem B: {_day(result.b.date_from)} - {_day(result.b.date_to)}, "
        f"toplam harcama {money(result.b.total_minor)}",
        f"Fark (A - B): {money(result.delta_minor)}",
    ]
    if result.delta_pct is not None:
        lines.append(f"Değişim: {percent(result.delta_pct)}")
    for change in result.top_categories:
        lines.append(
            f"Kategori {change.label}: A {money(change.a_minor)}, B {money(change.b_minor)}, "
            f"fark {money(change.delta_minor)}"
        )
    return "\n".join(lines)


def accept_answer(answer: str, facts: str) -> str | None:
    """The answer trimmed to two sentences, or None when it is empty or uses a number that is not
    written in the facts (the model must not calculate)."""
    text = " ".join(answer.split())
    if not text:
        return None
    allowed = set(_NUMBER.findall(facts))
    if any(number not in allowed for number in _NUMBER.findall(text)):
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text)
    text = " ".join(sentences[:MAX_SENTENCES])
    if len(text) > MAX_CHARS:
        return None
    return text


class CommentaryCache:
    """A small time-limited cache: (user id, hash of the facts) -> answer (also a None answer is
    not stored, so a failed call is tried again next time)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: OrderedDict[tuple[uuid.UUID, str], tuple[float, str]] = OrderedDict()

    @staticmethod
    def key(user_id: uuid.UUID, facts: str) -> tuple[uuid.UUID, str]:
        return user_id, hashlib.sha256(facts.encode("utf-8")).hexdigest()

    def get(self, key: tuple[uuid.UUID, str]) -> str | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, text = item
        if self._clock() - stored_at > CACHE_TTL_SECONDS:
            del self._items[key]
            return None
        return text

    def put(self, key: tuple[uuid.UUID, str], text: str) -> None:
        self._items[key] = (self._clock(), text)
        self._items.move_to_end(key)
        while len(self._items) > CACHE_SIZE:
            self._items.popitem(last=False)


def write_commentary(
    provider: AIProvider | None,
    cache: CommentaryCache,
    user_id: uuid.UUID,
    result: CompareOut,
) -> str | None:
    """Blocking (the provider is synchronous): call it in a worker thread."""
    if provider is None:
        return None
    facts = build_facts(result)
    key = cache.key(user_id, facts)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        answer = provider.write_commentary(facts)
    except ProviderError:
        logger.warning("commentary_failed")
        return None
    except Exception:  # noqa: BLE001  (the commentary is optional: never break the screen)
        logger.warning("commentary_failed")
        return None
    accepted = accept_answer(answer, facts)
    if accepted is None:
        logger.warning("commentary_rejected")
        return None
    cache.put(key, accepted)
    return accepted
