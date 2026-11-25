"""Data shapes of the receipt extraction (spec 5.2).

Two layers, on purpose:

* `RawReceiptExtraction` is what the LLM returns. Every value is copied from the text as plain
  text ("494,60", "14.11.2026"): the model never converts, rounds or adds anything up.
* `ReceiptExtraction` is the spec 5.2 shape: real dates and `Decimal` amounts. It is produced
  only by `app/ai/validation.py`, which parses the raw strings deterministically and checks them
  against the receipt text.
"""

from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

PaymentMethod = Literal["CARD", "CASH", "UNKNOWN"]


class Confidence(StrEnum):
    """Spec 5.4. Never shown to users as a number."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---- what the LLM returns --------------------------------------------------------------------
# No defaults anywhere: the JSON schema sent to the model then marks every field as required
# (nullable where the receipt may not have it), which is what constrained output wants.


class RawReceiptItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name_raw: str
    quantity: str | None
    unit_price: str | None
    total_price: str | None


class RawReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    merchant_raw: str | None
    date: str | None
    time: str | None
    total: str | None
    payment_method: PaymentMethod
    installment_count: int | None
    items: list[RawReceiptItem]


# ---- bank screenshot rows (spec 5.5) ---------------------------------------------------------


class RawBankRow(BaseModel):
    """One row of a bank screen as the model copied it. Plain text again: `amount_text` keeps the
    sign and the currency word as printed ("-16.128,33 TL", "+160.855,99 TL", "-27,84 Bonus"),
    because the sign is how the direction is read and the word tells TL from points."""

    model_config = ConfigDict(extra="ignore")

    merchant_raw: str
    amount_text: str
    date_text: str | None
    time: str | None
    installment_text: str | None
    is_pending: bool


class RawBankExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rows: list[RawBankRow]


# ---- the validated result (spec 5.2) ---------------------------------------------------------


class ReceiptItem(BaseModel):
    name_raw: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None


class ReceiptExtraction(BaseModel):
    merchant_raw: str | None
    date: date | None  # never guessed; null if absent or not credible
    time: time | None
    total: Decimal | None
    currency: str = "TRY"
    payment_method: PaymentMethod = "UNKNOWN"
    installment_count: int | None
    items: list[ReceiptItem] = []


# ---- the comparison commentary (P11) ----------------------------------------------------------


class RawCommentary(BaseModel):
    """What the model returns for the comparison commentary: one or two Turkish sentences."""

    model_config = ConfigDict(extra="ignore")

    text: str
