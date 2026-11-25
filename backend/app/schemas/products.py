"""Products, warranties, return windows, suggestions and refunds (spec 10, 9, P12).
Money: `*_minor` (kuruş). Every default carries its `source`."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    CategoryKey,
    Channel,
    ProductStatus,
    ReturnWindowSource,
    ReturnWindowStatus,
    WarrantySource,
)
from app.schemas.documents import DocumentOut

MAX_PRICE_MINOR = 100_000_000_000  # 1 billion TRY: far above any purchase, far below BIGINT


class WarrantyOut(BaseModel):
    start_date: dt.date | None
    end_date: dt.date
    source: WarrantySource
    # False while the 2-year default has not been accepted or edited by the user.
    confirmed: bool
    days_left: int


class ReturnWindowOut(BaseModel):
    end_date: dt.date
    source: ReturnWindowSource
    status: ReturnWindowStatus
    days_left: int


class ProductOut(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID | None
    receipt_item_id: uuid.UUID | None
    name: str
    brand: str | None
    model: str | None
    serial_number: str | None
    category_key: CategoryKey | None
    purchase_date: dt.date | None
    purchase_price_minor: int | None
    status: ProductStatus
    # From the purchase, when the product came from one.
    merchant_display: str | None
    channel: Channel | None
    warranty: WarrantyOut | None
    return_window: ReturnWindowOut | None
    document_count: int


class ProductDetail(ProductOut):
    # Installments: what the bank charges in all minus the purchase total (spec 10.3), when > 0.
    financing_cost_minor: int | None
    # How much of the purchase can still be refunded (null without a purchase).
    refundable_minor: int | None
    # The product's own files (warranty card ...) and the purchase's receipt / invoice.
    documents: list[DocumentOut]


class ProductList(BaseModel):
    items: list[ProductOut]


class ProductIn(BaseModel):
    """From a purchase (`transaction_id`), one line of its receipt (`receipt_item_id`) or by hand.
    Empty fields are filled from the purchase / line; a product by hand needs a name."""

    transaction_id: uuid.UUID | None = None
    receipt_item_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    category_key: CategoryKey | None = None
    purchase_date: dt.date | None = None
    purchase_price_minor: int | None = Field(default=None, ge=0, le=MAX_PRICE_MINOR)
    # Only for a product by hand (a purchase has its own): decides the return-window default.
    channel: Channel | None = None


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    category_key: CategoryKey | None = None
    purchase_date: dt.date | None = None
    purchase_price_minor: int | None = Field(default=None, ge=0, le=MAX_PRICE_MINOR)
    # ARCHIVED ("Arşivle") or ACTIVE again; RETURNED only for a product without a purchase (a
    # product with one is returned through a refund).
    status: ProductStatus | None = None


class WarrantyIn(BaseModel):
    end_date: dt.date
    start_date: dt.date | None = None
    # LEGAL_DEFAULT only for the 2-year default itself (accepting it); otherwise DOCUMENT / USER.
    source: WarrantySource
    confirmed: bool = True


class ReturnWindowIn(BaseModel):
    end_date: dt.date
    # LEGAL_DEFAULT only for the 14-day default of an online purchase.
    source: ReturnWindowSource


class ProductSuggestionOut(BaseModel):
    """A purchase (or a line of its receipt) worth tracking as a product (spec 10.1)."""

    transaction_id: uuid.UUID
    receipt_item_id: uuid.UUID | None
    name: str
    merchant_display: str
    category_key: CategoryKey
    purchase_date: dt.date
    price_minor: int


class ProductSuggestionList(BaseModel):
    items: list[ProductSuggestionOut]


class DismissIn(BaseModel):
    transaction_id: uuid.UUID
    receipt_item_id: uuid.UUID | None = None


# ---- refunds ------------------------------------------------------------------------------------


class RefundIn(BaseModel):
    amount_minor: int = Field(gt=0, le=MAX_PRICE_MINOR)
    date: dt.date
    # The product that went back (it becomes RETURNED). Without it, a refund of the whole
    # remaining amount returns every active product of the purchase.
    product_id: uuid.UUID | None = None


class RefundLinkIn(BaseModel):
    transaction_id: uuid.UUID


class RefundCandidateOut(BaseModel):
    transaction_id: uuid.UUID
    merchant_display: str
    category_key: CategoryKey | None
    purchase_date: dt.date
    total_minor: int
    refundable_minor: int
    # Higher is a better fit (amount equal to the remaining amount, close in time).
    score: float


class RefundSuggestionOut(BaseModel):
    """A bank CREDIT row and the purchases it may be a refund of (suggestion only)."""

    observation_id: uuid.UUID
    merchant_raw: str | None
    amount_minor: int
    obs_date: dt.date
    candidates: list[RefundCandidateOut]


class RefundSuggestionList(BaseModel):
    items: list[RefundSuggestionOut]


AttentionKind = Literal["RETURN", "WARRANTY"]
