"""Documents, products, warranties and return windows (spec section 10).

Unknown dates stay NULL; defaults are *suggestions* carrying a `source` label (invariant 7).
"""

import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR

from app.models.base import (
    Base,
    TimestampMixin,
    UserOwnedMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    money_column,
)
from app.models.enums import (
    DocumentType,
    ProductStatus,
    ReturnWindowSource,
    ReturnWindowStatus,
    WarrantySource,
)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_user_id", "user_id"),)

    # Deleting the transaction keeps the product (spec 6.3): the link is just cleared.
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    receipt_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("receipt_items.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    product_category: Mapped[str | None] = mapped_column(String(30))  # a category key
    purchase_date: Mapped[date | None] = mapped_column(Date)
    # NULL = unknown price (e.g. a product added by hand); never replaced by 0.
    purchase_price_minor: Mapped[int | None] = money_column("purchase_price_minor", nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        enum_type(ProductStatus, "status"), nullable=False, server_default="ACTIVE"
    )


class Document(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    """Metadata of a stored file. The bytes live in private storage under `storage_key`."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_id", "user_id"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonneg"),
    )

    type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType, "type"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL")
    )


class Warranty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One per product. Reached through its product (which carries user_id)."""

    __tablename__ = "warranties"
    __table_args__ = (
        CheckConstraint("start_date IS NULL OR start_date <= end_date", name="start_not_after_end"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[WarrantySource] = mapped_column(
        enum_type(WarrantySource, "source"), nullable=False
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())


class ReturnWindow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One per product. Reached through its product (which carries user_id)."""

    __tablename__ = "return_windows"

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[ReturnWindowSource] = mapped_column(
        enum_type(ReturnWindowSource, "source"), nullable=False
    )
    status: Mapped[ReturnWindowStatus] = mapped_column(
        enum_type(ReturnWindowStatus, "status"), nullable=False, server_default="OPEN"
    )
