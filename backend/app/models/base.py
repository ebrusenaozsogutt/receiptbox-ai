"""Declarative base, shared mixins and column helpers."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Stable, predictable constraint names. Alembic needs them to drop constraints on downgrade.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserOwnedMixin:
    """Marks a table as user-owned. Every query on such a table must filter by user_id."""

    @declared_attr.directive
    def user_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805 (SQLAlchemy declared_attr convention)
        return mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def enum_type(enum_class: type[enum.Enum], name: str) -> SAEnum:
    """VARCHAR + CHECK constraint (not a native PostgreSQL enum), storing the member values."""
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


def money_column(name: str, *, nullable: bool = False, **kwargs: Any):  # noqa: ANN201
    """Integer minor units (kuruş), never negative. NULL is allowed only where stated."""
    return mapped_column(
        name,
        BigInteger,
        CheckConstraint(f"{name} >= 0", name=f"{name}_nonneg"),
        nullable=nullable,
        **kwargs,
    )
