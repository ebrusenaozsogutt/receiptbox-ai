import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.schemas import Confidence, ReceiptExtraction
from app.models.enums import CategoryKey


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
