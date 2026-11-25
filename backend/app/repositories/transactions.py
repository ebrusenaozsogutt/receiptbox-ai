"""Transactions (canonical purchases). Every method takes `user_id` and filters by it, and every
read leaves out soft-deleted rows (`deleted_at` set)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Category, Document, Observation, ReceiptItem, Transaction
from app.models.enums import (
    CategoryKey,
    Channel,
    ObservationStatus,
    PaymentType,
    TransactionKind,
)


@dataclass(frozen=True)
class TransactionRow:
    transaction: Transaction
    category_key: CategoryKey | None
    document_count: int
    # P12: the sum of the (not deleted) refunds of this purchase.
    refunded_minor: int = 0


@dataclass(frozen=True)
class Page:
    rows: list[TransactionRow]
    count: int
    sum_minor: int


def _require_uuid(user_id: object) -> None:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: uuid.UUID,
        *,
        merchant_id: uuid.UUID | None,
        merchant_display: str,
        category_id: uuid.UUID | None,
        purchase_date: date,
        purchase_time: time | None,
        total_minor: int,
        payment_type: PaymentType,
        channel: Channel,
        note: str | None,
        is_estimated: bool = False,
    ) -> Transaction:
        _require_uuid(user_id)
        transaction = Transaction(
            user_id=user_id,
            merchant_id=merchant_id,
            merchant_display=merchant_display,
            category_id=category_id,
            purchase_date=purchase_date,
            purchase_time=purchase_time,
            total_minor=total_minor,
            currency="TRY",
            payment_type=payment_type,
            channel=channel,
            kind=TransactionKind.PURCHASE,
            is_estimated=is_estimated,
            note=note,
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction

    async def get(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None:
        _require_uuid(user_id)
        statement = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_row(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> TransactionRow | None:
        page = await self.list(user_id, transaction_id=transaction_id, limit=1, offset=0)
        return page.rows[0] if page.rows else None

    async def list(
        self,
        user_id: uuid.UUID,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        category: CategoryKey | None = None,
        merchant_id: uuid.UUID | None = None,
        search: str | None = None,
        transaction_id: uuid.UUID | None = None,
        limit: int,
        offset: int,
    ) -> Page:
        _require_uuid(user_id)
        conditions = [
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
        ]
        if transaction_id is not None:
            conditions.append(Transaction.id == transaction_id)
        else:
            # P12: a refund of a purchase is shown on that purchase (and counted in its month, as
            # the analytics do), not as an item of its own; a refund without one stays an item.
            conditions.append(
                or_(
                    Transaction.kind == TransactionKind.PURCHASE,
                    Transaction.refund_of_id.is_(None),
                )
            )
        if date_from is not None:
            conditions.append(Transaction.purchase_date >= date_from)
        if date_to is not None:
            conditions.append(Transaction.purchase_date <= date_to)
        if category is not None:
            conditions.append(Category.key == category)
        if merchant_id is not None:
            conditions.append(Transaction.merchant_id == merchant_id)
        if search:
            pattern = f"%{_escape_like(search.strip())}%"
            conditions.append(
                or_(
                    Transaction.merchant_display.ilike(pattern, escape="\\"),
                    Transaction.note.ilike(pattern, escape="\\"),
                )
            )

        refund = aliased(Transaction)
        refunded = func.coalesce(
            select(func.sum(refund.total_minor))
            .where(
                refund.refund_of_id == Transaction.id,
                refund.user_id == user_id,
                refund.kind == TransactionKind.REFUND,
                refund.deleted_at.is_(None),
            )
            .scalar_subquery(),
            0,
        )
        signed_total = case(
            (Transaction.kind == TransactionKind.REFUND, -Transaction.total_minor),
            else_=Transaction.total_minor - refunded,
        )
        totals = (
            select(func.count(Transaction.id), func.coalesce(func.sum(signed_total), 0))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(*conditions)
        )
        count, sum_minor = (await self._session.execute(totals)).one()

        documents = (
            select(func.count(Document.id))
            .where(Document.transaction_id == Transaction.id, Document.user_id == user_id)
            .scalar_subquery()
        )
        statement = (
            select(Transaction, Category.key, documents, refunded)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(*conditions)
            .order_by(
                Transaction.purchase_date.desc(),
                Transaction.purchase_time.desc().nulls_last(),
                Transaction.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = [
            TransactionRow(transaction, key, doc_count, int(refunded_sum))
            for transaction, key, doc_count, refunded_sum in (
                await self._session.execute(statement)
            ).all()
        ]
        return Page(rows=rows, count=count, sum_minor=int(sum_minor))

    async def evidence(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Sequence[Observation]:
        _require_uuid(user_id)
        statement = (
            select(Observation)
            .where(Observation.user_id == user_id, Observation.transaction_id == transaction_id)
            .order_by(Observation.created_at)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def items_of(
        self, user_id: uuid.UUID, observation_ids: Sequence[uuid.UUID]
    ) -> Sequence[ReceiptItem]:
        """Receipt items, reached through their observations (which carry the user id)."""
        _require_uuid(user_id)
        if not observation_ids:
            return []
        statement = (
            select(ReceiptItem)
            .join(Observation, Observation.id == ReceiptItem.observation_id)
            .where(Observation.user_id == user_id, ReceiptItem.observation_id.in_(observation_ids))
            .order_by(ReceiptItem.observation_id, ReceiptItem.position, ReceiptItem.id)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def documents_of(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Sequence[Document]:
        _require_uuid(user_id)
        statement = (
            select(Document)
            .where(Document.user_id == user_id, Document.transaction_id == transaction_id)
            .order_by(Document.created_at)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def soft_delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        """Spec 6.3: the transaction is soft-deleted and its observations are detached (they stay
        CONFIRMED but no longer point at it, so they can be linked again later)."""
        _require_uuid(user_id)
        await self._session.execute(
            update(Observation)
            .where(Observation.user_id == user_id, Observation.transaction_id == transaction_id)
            .values(transaction_id=None, status=ObservationStatus.CONFIRMED)
        )
        await self._session.execute(
            update(Transaction)
            .where(Transaction.id == transaction_id, Transaction.user_id == user_id)
            .values(deleted_at=datetime.now().astimezone())
        )
        await self._session.flush()
