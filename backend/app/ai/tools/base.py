"""The building blocks of the assistant's tools (spec 13.2, P14).

A tool is: a Pydantic argument model (its JSON schema is what the model sees), an async executor
that calls the existing services with the SERVER-INJECTED `user_id` (never an argument: the
argument models forbid unknown fields), a function that turns its result into deep-link actions
and a function that writes a short Turkish answer from its result (used when the model's own
answer fails the number check).

What a tool returns is what the model reads. It holds no kuruş integers: every amount is already
formatted (`"1.349,90 TL"`), so the model copies numbers and never calculates them.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.money import format_minor
from app.models.enums import CategoryKey
from app.services.installment_schedule import add_months, first_of_month
from app.storage.backend import StorageBackend

# The Turkish labels of the 13 categories (the seed of migration 0002; a test compares them).
CATEGORY_LABELS: dict[CategoryKey, str] = {
    CategoryKey.GROCERY: "Market",
    CategoryKey.FOOD_DRINK: "Yeme-İçme",
    CategoryKey.TRANSPORT: "Ulaşım",
    CategoryKey.FUEL: "Yakıt",
    CategoryKey.CLOTHING: "Giyim",
    CategoryKey.TECHNOLOGY: "Teknoloji",
    CategoryKey.HOME: "Ev & Yaşam",
    CategoryKey.HEALTH_CARE: "Sağlık & Kişisel Bakım",
    CategoryKey.ENTERTAINMENT: "Eğlence",
    CategoryKey.SUBSCRIPTION: "Abonelik",
    CategoryKey.EDUCATION: "Eğitim",
    CategoryKey.BILLS: "Fatura & Hizmetler",
    CategoryKey.OTHER: "Diğer",
}

MONTHS_TR = (
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

# How far back and ahead a date argument may reach; outside it is clamped (spec 13.1: the backend
# re-validates the dates the model resolved).
YEARS_BACK = 10
YEARS_AHEAD = 1
MAX_SCHEDULE_MONTHS = 24
MAX_PLAN_MONTHS = 36


class ToolArgumentError(Exception):
    """Arguments the model must fix. The message goes back to the model (never user data)."""


class ToolArgs(BaseModel):
    """Unknown fields (a `user_id`, say) are an error, not ignored."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    settings: Settings
    storage: StorageBackend
    user_id: uuid.UUID
    today: date


@dataclass(frozen=True)
class Action:
    """A deep link into the app, shown as a button under the answer."""

    type: str  # OPEN_TRANSACTIONS | OPEN_PRODUCT | OPEN_DOCUMENT | OPEN_INSTALLMENTS
    label: str
    params: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "label": self.label, "params": dict(self.params)}


Output = dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[ToolArgs]
    run: Callable[[ToolContext, Any], Awaitable[Output]]
    actions: Callable[[Any, Output], list[Action]]
    summary: Callable[[Any, Output], str]

    def parameters_schema(self) -> dict[str, Any]:
        return inline_schema(self.args_model.model_json_schema())


# ---- formatting (what the model reads and copies) ------------------------------------------------


def tl(minor: int) -> str:
    """134990 -> '1.349,90 TL'."""
    return f"{format_minor(minor)} TL"


def day_tr(value: date) -> str:
    """'26 Kasım 2026'."""
    return f"{value.day} {MONTHS_TR[value.month - 1]} {value.year}"


def month_tr(value: date) -> str:
    """'Kasım 2026'."""
    return f"{MONTHS_TR[value.month - 1]} {value.year}"


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def percent_tr(value: float) -> str:
    """12.5 -> '%12,5'."""
    return "%" + f"{value:.1f}".replace(".", ",")


def period_out(date_from: date, date_to: date) -> dict[str, str]:
    return {"from": date_from.isoformat(), "to": date_to.isoformat()}


def period_tr(date_from: date, date_to: date) -> str:
    return f"{day_tr(date_from)} - {day_tr(date_to)}"


# ---- argument checks -------------------------------------------------------------------------


def date_bounds(today: date) -> tuple[date, date]:
    return date(today.year - YEARS_BACK, 1, 1), date(today.year + YEARS_AHEAD, 12, 31)


def clamp_period(today: date, date_from: date, date_to: date) -> tuple[date, date]:
    """Reject a reversed period; move both ends into the supported range."""
    if date_from > date_to:
        raise ToolArgumentError("date_from is after date_to; send the period in the right order.")
    low, high = date_bounds(today)
    if date_to < low or date_from > high:
        raise ToolArgumentError(
            f"The period must lie between {low.isoformat()} and {high.isoformat()}."
        )
    return max(date_from, low), min(date_to, high)


def clamp_day(today: date, value: date | None) -> date | None:
    if value is None:
        return None
    low, high = date_bounds(today)
    return min(max(value, low), high)


def clamp_int(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


def clamp_months(today: date, month_from: date, month_to: date) -> tuple[date, date]:
    """First days of months; at most MAX_SCHEDULE_MONTHS months long."""
    month_from, month_to = first_of_month(month_from), first_of_month(month_to)
    if month_from > month_to:
        raise ToolArgumentError("month_from is after month_to; send the months in the right order.")
    low, _ = date_bounds(today)
    # Installment plans run up to 36 months, so the schedule may look further ahead than spending.
    high = add_months(first_of_month(today), MAX_PLAN_MONTHS)
    month_from = max(month_from, first_of_month(low))
    month_to = min(month_to, high, add_months(month_from, MAX_SCHEDULE_MONTHS - 1))
    if month_from > month_to:
        raise ToolArgumentError("The months are outside the supported range.")
    return month_from, month_to


# ---- JSON schema for the providers -----------------------------------------------------------


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic's schema with `$ref`s resolved and titles dropped: the plain subset of JSON
    schema every function-calling API accepts."""
    definitions = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return resolve(definitions[name])
            options = node.get("anyOf")
            if isinstance(options, list):
                # `X | None` -> X: an optional argument is simply not required.
                real = [o for o in options if o != {"type": "null"}]
                if len(real) == 1 and len(real) < len(options):
                    merged = {k: v for k, v in node.items() if k not in ("anyOf", "default")}
                    return resolve({**real[0], **merged})
            return {
                key: resolve(value) for key, value in node.items() if key not in ("$defs", "title")
            }
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)
