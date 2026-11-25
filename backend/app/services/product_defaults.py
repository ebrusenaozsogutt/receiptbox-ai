"""Spec 10.2: the suggested warranty and return-window ends. Pure functions, no database.

They are SUGGESTIONS carrying a source label (invariant 7), never silent facts:
- Warranty end = purchase date + 2 years, `LEGAL_DEFAULT`: the statutory minimum warranty for new
  goods (Law No. 6502, art. 56). It stays unconfirmed until the user accepts or edits it.
- Return window, ONLINE purchase = purchase date + 14 days, `LEGAL_DEFAULT`: the right of
  withdrawal for distance sales (art. 48; legally counted from delivery, so the user can adjust).
- IN_STORE / UNKNOWN: no default. In-store returns are store policy: the user enters it
  (`STORE_POLICY` or `USER`).
"""

from datetime import date, timedelta

from app.models.enums import Channel
from app.services.installment_schedule import add_months

WARRANTY_YEARS = 2
RETURN_DAYS_ONLINE = 14


def default_warranty_end(purchase_date: date) -> date:
    """Purchase date + 2 years (29 February -> 28 February)."""
    return add_months(purchase_date, 12 * WARRANTY_YEARS)


def default_return_end(purchase_date: date, channel: Channel) -> date | None:
    """Purchase date + 14 days for an online purchase; None (ask the user) otherwise."""
    if channel != Channel.ONLINE:
        return None
    return purchase_date + timedelta(days=RETURN_DAYS_ONLINE)


def days_left(end: date, today: date) -> int:
    """Days until `end` (0 = ends today, negative = over)."""
    return (end - today).days
