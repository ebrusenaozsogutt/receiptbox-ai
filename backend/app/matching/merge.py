"""The fields of a purchase that a merge may change, and how they are kept for "Ayır" (spec 7.5).

`TxFields` is a purchase as one source saw it: the merchant, the category, the date and time, the
total and the channel. Three copies are written to `match_decisions.merge_snapshot` when two
observations are merged:

* `before`    the transaction just before the merge (what the first observation made of it);
* `incoming`  what the new observation would have been on its own (as the user reviewed it);
* `after`     the transaction after the merge (the higher source wins, `SOURCE_PRECEDENCE`).

Unmerging gives the leaving observation a new transaction made from its own copy and puts the
other copy back on the old transaction, field by field, but only where the user did not change the
field since the merge (a field that is no longer equal to `after` is left alone).
"""

import uuid
from dataclasses import dataclass, fields
from datetime import date, time
from typing import Any

from app.models import Transaction
from app.models.enums import Channel


@dataclass(frozen=True)
class TxFields:
    merchant_id: uuid.UUID | None
    merchant_display: str
    category_id: uuid.UUID | None
    purchase_date: date
    purchase_time: time | None
    total_minor: int
    channel: Channel

    @classmethod
    def of(cls, transaction: Transaction) -> "TxFields":
        return cls(
            merchant_id=transaction.merchant_id,
            merchant_display=transaction.merchant_display,
            category_id=transaction.category_id,
            purchase_date=transaction.purchase_date,
            purchase_time=transaction.purchase_time,
            total_minor=transaction.total_minor,
            channel=transaction.channel,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "merchant_id": str(self.merchant_id) if self.merchant_id else None,
            "merchant_display": self.merchant_display,
            "category_id": str(self.category_id) if self.category_id else None,
            "purchase_date": self.purchase_date.isoformat(),
            "purchase_time": self.purchase_time.isoformat() if self.purchase_time else None,
            "total_minor": self.total_minor,
            "channel": self.channel.value,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TxFields":
        return cls(
            merchant_id=uuid.UUID(data["merchant_id"]) if data.get("merchant_id") else None,
            merchant_display=data["merchant_display"],
            category_id=uuid.UUID(data["category_id"]) if data.get("category_id") else None,
            purchase_date=date.fromisoformat(data["purchase_date"]),
            purchase_time=time.fromisoformat(data["purchase_time"])
            if data.get("purchase_time")
            else None,
            total_minor=int(data["total_minor"]),
            channel=Channel(data["channel"]),
        )


FIELD_NAMES = tuple(f.name for f in fields(TxFields))


def apply_fields(
    transaction: Transaction, values: TxFields, *, keep_channel_if_unknown: bool
) -> None:
    """Write `values` onto the transaction. A channel of UNKNOWN never replaces a known one when
    `keep_channel_if_unknown` (a bank row does not know whether it was a shop or a web order)."""
    transaction.merchant_id = values.merchant_id
    transaction.merchant_display = values.merchant_display
    transaction.category_id = values.category_id
    transaction.purchase_date = values.purchase_date
    transaction.purchase_time = values.purchase_time
    transaction.total_minor = values.total_minor
    if not (keep_channel_if_unknown and values.channel == Channel.UNKNOWN):
        transaction.channel = values.channel


def revert_fields(transaction: Transaction, after: TxFields, target: TxFields) -> None:
    """Put `target` back, field by field, where the transaction still holds what the merge left
    (`after`). A field the user edited since is not touched."""
    current = TxFields.of(transaction)
    for name in FIELD_NAMES:
        if getattr(current, name) == getattr(after, name):
            setattr(transaction, name, getattr(target, name))
