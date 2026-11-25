"""Refunds (spec 9, P12): a REFUND transaction pointing at the purchase it refunds.

- The amount is at most what is left of the purchase (its total minus earlier refunds); partial
  refunds are allowed. Spending is reduced in the ORIGINAL purchase's month (analytics, P11).
- The returned product becomes RETURNED, its return window RETURNED, and its pending reminders are
  deleted. Without a product, a refund of the whole remaining amount returns every active product
  of the purchase.
- A bank CREDIT row is only ever SUGGESTED as a refund (`refund_matcher`); the user links it.
Nothing here commits: the caller (TransactionService) commits after the budget check.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, RefundTooLargeError, ValidationFailedError
from app.matching import refund_matcher
from app.models import Category, Product, Transaction
from app.models.enums import (
    CategoryKey,
    Direction,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    ProductStatus,
    ReturnWindowStatus,
    TransactionKind,
)
from app.models.transaction import Observation
from app.repositories.products import ProductRepository
from app.schemas.products import RefundCandidateOut


def merchant_id_of(observation: Observation) -> uuid.UUID | None:
    """The merchant the bank import recognised for this row (stored with its suggestions)."""
    suggestions = (observation.extraction_json or {}).get("suggestions") or {}
    value = (suggestions.get("merchant") or {}).get("merchant_id")
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


class RefundService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._products = ProductRepository(session)

    async def purchase(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        """One of the user's purchases that is not deleted (404 otherwise)."""
        statement = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.kind == TransactionKind.PURCHASE,
        )
        found = (await self._session.execute(statement)).scalar_one_or_none()
        if found is None:
            raise NotFoundError()
        return found

    async def refundable(self, user_id: uuid.UUID, purchase: Transaction) -> int:
        refunded = (await self._products.refunded(user_id, [purchase.id])).get(purchase.id, 0)
        return max(0, purchase.total_minor - refunded)

    async def refund(
        self,
        user_id: uuid.UUID,
        purchase: Transaction,
        *,
        amount_minor: int,
        day: date,
        today: date,
        product_id: uuid.UUID | None = None,
    ) -> Transaction:
        if not purchase.purchase_date <= day <= today:
            raise ValidationFailedError("The refund date must be between the purchase and today.")
        remaining = await self.refundable(user_id, purchase)
        if amount_minor > remaining:
            raise RefundTooLargeError()
        returned: list[Product] = []
        if product_id is not None:
            product = await self._products.get(user_id, product_id)
            if product is None or product.transaction_id != purchase.id:
                raise NotFoundError()
            returned = [product]
        elif amount_minor == remaining:
            returned = [
                p
                for p in await self._products.of_transaction(user_id, purchase.id)
                if p.status == ProductStatus.ACTIVE
            ]
        refund = Transaction(
            user_id=user_id,
            merchant_id=purchase.merchant_id,
            merchant_display=purchase.merchant_display,
            category_id=purchase.category_id,
            purchase_date=day,
            total_minor=amount_minor,
            currency=purchase.currency,
            payment_type=PaymentType.SINGLE,
            channel=purchase.channel,
            kind=TransactionKind.REFUND,
            refund_of_id=purchase.id,
        )
        self._session.add(refund)
        await self._session.flush()
        await self.mark_returned(user_id, returned)
        return refund

    async def mark_returned(self, user_id: uuid.UUID, products: list[Product]) -> None:
        """RETURNED, the return window RETURNED, the pending reminders gone."""
        for product in products:
            product.status = ProductStatus.RETURNED
            window = await self._products.return_window(product.id)
            if window is not None:
                window.status = ReturnWindowStatus.RETURNED
        await self._products.delete_reminders(user_id, [p.id for p in products])
        await self._session.flush()

    # ---- bank CREDIT rows -----------------------------------------------------------------------

    async def candidates(
        self, user_id: uuid.UUID, observation: Observation
    ) -> list[RefundCandidateOut]:
        """The purchases this CREDIT row may refund (suggestion only, best first)."""
        if observation.amount_minor is None or observation.obs_date is None:
            return []
        day = observation.obs_date
        statement = (
            select(Transaction, Category.key)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                Transaction.kind == TransactionKind.PURCHASE,
                Transaction.purchase_date >= day - timedelta(days=refund_matcher.MAX_DAYS),
                Transaction.purchase_date <= day,
            )
        )
        rows = (await self._session.execute(statement)).all()
        refunded = await self._products.refunded(user_id, [t.id for t, _ in rows])
        keys = {t.id: key for t, key in rows}
        purchases = [
            refund_matcher.Purchase(
                transaction_id=t.id,
                merchant_id=t.merchant_id,
                merchant=t.merchant_display,
                total_minor=t.total_minor,
                refundable_minor=max(0, t.total_minor - refunded.get(t.id, 0)),
                day=t.purchase_date,
            )
            for t, _ in rows
        ]
        row = refund_matcher.CreditRow(
            merchant_id=merchant_id_of(observation),
            merchant=observation.merchant_raw or "",
            amount_minor=observation.amount_minor,
            day=day,
        )
        return [
            RefundCandidateOut(
                transaction_id=c.purchase.transaction_id,
                merchant_display=c.purchase.merchant,
                category_key=CategoryKey(keys[c.purchase.transaction_id])
                if keys[c.purchase.transaction_id]
                else None,
                purchase_date=c.purchase.day,
                total_minor=c.purchase.total_minor,
                refundable_minor=c.purchase.refundable_minor,
                score=c.score,
            )
            for c in refund_matcher.candidates(row, purchases)
        ]

    async def pending_credit_rows(self, user_id: uuid.UUID) -> list[Observation]:
        statement = (
            select(Observation)
            .where(
                Observation.user_id == user_id,
                Observation.source == ObservationSource.BANK_SCREENSHOT,
                Observation.status == ObservationStatus.PENDING_REVIEW,
                Observation.direction == Direction.CREDIT,
            )
            .order_by(Observation.obs_date.desc().nulls_last(), Observation.created_at)
        )
        return list((await self._session.execute(statement)).scalars())
