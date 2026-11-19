"""Request and response shapes for observations (review) and transactions.

Money is `*_minor`: integer kuruş, never a decimal or a float (spec 6). The review screen edits
what the extraction found and sends it back as these integers.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import (
    CategoryKey,
    Channel,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    TransactionKind,
)
from app.schemas.documents import DocumentOut

MAX_TOTAL_MINOR = 100_000_000  # 1,000,000 TRY, the same sanity limit as the extraction (5.3)
_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
_Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ItemIn(BaseModel):
    name_raw: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    quantity: Decimal | None = Field(default=None, gt=0, lt=1_000_000_000, decimal_places=3)
    unit_price_minor: int | None = Field(default=None, ge=0, lt=MAX_TOTAL_MINOR)
    total_price_minor: int | None = Field(default=None, ge=0, lt=MAX_TOTAL_MINOR)


class ConfirmRequest(BaseModel):
    """What the user saw on the review screen, after editing."""

    merchant_display: _Name
    date: dt.date
    time: dt.time | None = None
    total_minor: int = Field(gt=0, lt=MAX_TOTAL_MINOR)
    category_key: CategoryKey
    channel: Channel = Channel.UNKNOWN
    note: _Note | None = None
    items: list[ItemIn] = Field(default_factory=list, max_length=200)
    remember_category_for_merchant: bool = False


class ManualTransactionRequest(BaseModel):
    merchant_display: _Name
    date: dt.date
    time: dt.time | None = None
    total_minor: int = Field(gt=0, lt=MAX_TOTAL_MINOR)
    category_key: CategoryKey
    channel: Channel = Channel.UNKNOWN
    note: _Note | None = None


class TransactionPatch(BaseModel):
    """Only the fields that are sent are changed. `time` and `note` may be set to null."""

    merchant_display: _Name | None = None
    date: dt.date | None = None
    time: dt.time | None = None
    total_minor: int | None = Field(default=None, gt=0, lt=MAX_TOTAL_MINOR)
    category_key: CategoryKey | None = None
    channel: Channel | None = None
    note: _Note | None = None

    @field_validator("merchant_display", "date", "total_minor", "category_key", "channel")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("this field cannot be null")
        return value


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_raw: str
    quantity: Decimal
    unit_price_minor: int | None
    total_price_minor: int | None


class EvidenceOut(BaseModel):
    """One observation attached to a transaction (receipt, QR, bank row, manual entry)."""

    id: uuid.UUID
    source: ObservationSource
    status: ObservationStatus
    merchant_raw: str | None
    amount_minor: int | None
    obs_date: dt.date | None
    obs_time: dt.time | None
    created_at: dt.datetime


class TransactionOut(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID | None
    merchant_display: str
    category_key: CategoryKey | None
    purchase_date: dt.date
    purchase_time: dt.time | None
    total_minor: int
    currency: str
    payment_type: PaymentType
    channel: Channel
    kind: TransactionKind
    is_estimated: bool
    note: str | None
    document_count: int
    created_at: dt.datetime


class TransactionDetail(TransactionOut):
    evidence: list[EvidenceOut]
    items: list[ItemOut]
    documents: list[DocumentOut]


class TransactionList(BaseModel):
    items: list[TransactionOut]
    count: int = Field(description="How many transactions match the filters (all pages).")
    sum_minor: int = Field(description="Net total of the matching ones: purchases minus refunds.")
    limit: int
    offset: int


class ObservationOut(BaseModel):
    """A pending observation for the review screen. The masked text and the raw model answer are
    not part of it."""

    id: uuid.UUID
    source: ObservationSource
    status: ObservationStatus
    merchant_raw: str | None
    amount_minor: int | None
    obs_date: dt.date | None
    obs_time: dt.time | None
    installment_count: int | None
    extraction: dict[str, Any] | None
    suggestions: dict[str, Any] | None
    confidence: dict[str, Any]
    items: list[ItemOut]
    transaction_id: uuid.UUID | None
    created_at: dt.datetime
