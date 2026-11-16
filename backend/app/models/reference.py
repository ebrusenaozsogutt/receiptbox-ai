"""Reference data: categories, merchants, aliases and per-user category rules."""

import uuid

from sqlalchemy import ForeignKey, Integer, PrimaryKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    TimestampMixin,
    UserOwnedMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
)
from app.models.enums import CategoryKey


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Seeded and read-only: the fixed 13 categories."""

    __tablename__ = "categories"

    key: Mapped[CategoryKey] = mapped_column(
        enum_type(CategoryKey, "key"), unique=True, nullable=False
    )
    label_tr: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Merchant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchants"

    canonical_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    default_category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("categories.id"))


class MerchantAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """user_id NULL means a global alias; otherwise the alias belongs to that user only."""

    __tablename__ = "merchant_aliases"
    __table_args__ = (
        # NULLS NOT DISTINCT: without it PostgreSQL would allow the same global alias twice.
        UniqueConstraint("alias_normalized", "user_id", postgresql_nulls_not_distinct=True),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    alias_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )


class UserCategoryRule(UserOwnedMixin, TimestampMixin, Base):
    """'Always put this merchant in this category' (spec 5.7, step 1)."""

    __tablename__ = "user_category_rules"
    # No UUID id: the primary key is (user_id, merchant_id), as in spec 6.1.
    __table_args__ = (PrimaryKeyConstraint("user_id", "merchant_id"),)

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False
    )
