import datetime as dt
import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.schemas import Confidence, ReceiptExtraction
from app.models.enums import CategoryKey, Direction
from app.schemas.installments import InstallmentPreviewOut
from app.schemas.matches import BankRowMatchOut


class ExtractReceiptRequest(BaseModel):
    """What the app sends after on-device OCR and masking (the P04 CapturePayload).

    `masked_text` is limited to 20 KB by the service (413 TEXT_TOO_LARGE); max_length here only
    keeps absurd bodies from being processed at all.
    """

    masked_text: str = Field(min_length=1, max_length=200_000)
    capture_date: date
    source: Literal["CAMERA", "GALLERY", "SHARE"]


class ExtractEinvoiceRequest(BaseModel):
    """The cleaned GİB QR (the phone has already removed the buyer's identity number) and,
    optionally, the masked invoice text."""

    qr_payload: dict[str, Any] | str
    masked_text: str | None = Field(default=None, max_length=200_000)
    capture_date: date


class MerchantSuggestion(BaseModel):
    """Which merchant this probably is (spec 5.6). `NEW` means unknown: `canonical_name` is only
    a proposed name and no merchant exists yet (it is created when the user confirms)."""

    match: Literal["USER_ALIAS", "GLOBAL_ALIAS", "FUZZY", "NEW", "NONE"]
    merchant_id: uuid.UUID | None = None
    canonical_name: str | None = None
    score: float | None = None


class CategorySuggestionOut(BaseModel):
    key: CategoryKey
    source: Literal["USER_RULE", "MERCHANT_DEFAULT", "LLM", "FALLBACK"]


class Suggestions(BaseModel):
    merchant: MerchantSuggestion
    category: CategorySuggestionOut


class ExtractReceiptResponse(BaseModel):
    observation_id: uuid.UUID
    extraction: ReceiptExtraction
    confidence: dict[str, Confidence]
    suggestions: Suggestions


class ExtractEinvoiceResponse(ExtractReceiptResponse):
    ai_used: bool = Field(description="True when the invoice text was read by the AI provider.")


class ExtractBankRequest(BaseModel):
    """What the app sends after on-device OCR and masking of a bank screenshot. The image itself
    never leaves the phone (spec 15.3). `bank_hint` is what the phone's keyword table guessed
    (or the user chose); an unknown or unsupported bank only means "no bank-specific help"."""

    masked_text: str = Field(min_length=1, max_length=200_000)
    bank_hint: str | None = Field(default=None, max_length=40)
    capture_date: date


class BankRowOut(BaseModel):
    """One row of the screenshot, saved as a pending observation (money is integer kuruş)."""

    observation_id: uuid.UUID
    merchant_raw: str
    amount_minor: int
    direction: Direction
    kind: Literal["PURCHASE", "REFUND"]
    date: dt.date | None
    time: dt.time | None
    installment_seq: int | None
    installment_count: int | None
    is_pending: bool
    # DUPLICATE: the same row was imported before (the screenshot overlaps an earlier one).
    status: Literal["PENDING_REVIEW", "DUPLICATE"]
    possible_refund: bool
    confidence: dict[str, Confidence]
    suggestions: Suggestions
    # P09: this row is (AUTO) or may be (SUGGEST) the same purchase as one you already saved.
    match: BankRowMatchOut | None = None
    # P10: what an installment row will become (a payment of a plan, an estimated purchase ...).
    installment: InstallmentPreviewOut | None = None


class SkippedRowOut(BaseModel):
    """A row that was found but is not imported: PAYMENT (a card-bill payment), HEADER_OR_TOTAL,
    NON_TL_AMOUNT (points), ZERO_AMOUNT, AMOUNT_NOT_IN_TEXT, BAD_AMOUNT, MASKED_MERCHANT."""

    merchant_raw: str
    amount_minor: int | None
    date: dt.date | None
    reason: str


class ExtractBankResponse(BaseModel):
    bank_key: str | None
    rows: list[BankRowOut]
    skipped: list[SkippedRowOut]
