"""Products, warranties, return windows, product suggestions and refunds (P12).

Every method takes `user_id` and filters by it. Warranties and return windows have no user_id
(spec 6.1): they are only reached through their product, which is filtered by user."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Category,
    Document,
    Product,
    ProductSuggestionDismissal,
    ReceiptItem,
    Reminder,
    ReturnWindow,
    Transaction,
    Warranty,
)
from app.models.enums import (
    CategoryKey,
    Channel,
    ObservationStatus,
    ProductStatus,
    ReminderType,
    ReturnWindowStatus,
    TransactionKind,
)
from app.models.transaction import Observation

PRODUCT_REMINDERS = (ReminderType.WARRANTY_EXPIRY, ReminderType.RETURN_DEADLINE)


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


@dataclass(frozen=True)
class ProductRow:
    product: Product
    warranty: Warranty | None
    return_window: ReturnWindow | None
    merchant_display: str | None
    channel: Channel | None
    document_count: int


@dataclass(frozen=True)
class SuggestionRow:
    transaction_id: uuid.UUID
    receipt_item_id: uuid.UUID | None
    name: str
    merchant_display: str
    category_key: CategoryKey
    purchase_date: date
    price_minor: int


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- products -------------------------------------------------------------------------------

    def _rows_statement(self, user_id: uuid.UUID):  # noqa: ANN202
        documents = (
            select(func.count(Document.id))
            .where(Document.product_id == Product.id, Document.user_id == user_id)
            .scalar_subquery()
        )
        return (
            select(
                Product,
                Warranty,
                ReturnWindow,
                Transaction.merchant_display,
                Transaction.channel,
                documents,
            )
            .outerjoin(Warranty, Warranty.product_id == Product.id)
            .outerjoin(ReturnWindow, ReturnWindow.product_id == Product.id)
            .outerjoin(
                Transaction,
                and_(
                    Transaction.id == Product.transaction_id,
                    Transaction.user_id == user_id,
                    Transaction.deleted_at.is_(None),
                ),
            )
            .where(Product.user_id == user_id)
        )

    async def rows(
        self, user_id: uuid.UUID, *, statuses: Sequence[ProductStatus] | None = None
    ) -> list[ProductRow]:
        _check_user_id(user_id)
        statement = self._rows_statement(user_id)
        if statuses:
            statement = statement.where(Product.status.in_(statuses))
        statement = statement.order_by(Product.purchase_date.desc().nulls_last(), Product.name)
        return [ProductRow(*row) for row in (await self._session.execute(statement)).all()]

    async def row(self, user_id: uuid.UUID, product_id: uuid.UUID) -> ProductRow | None:
        _check_user_id(user_id)
        statement = self._rows_statement(user_id).where(Product.id == product_id)
        found = (await self._session.execute(statement)).first()
        return ProductRow(*found) if found else None

    async def get(self, user_id: uuid.UUID, product_id: uuid.UUID) -> Product | None:
        _check_user_id(user_id)
        statement = select(Product).where(Product.id == product_id, Product.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, user_id: uuid.UUID, **values: object) -> Product:
        _check_user_id(user_id)
        product = Product(user_id=user_id, **values)
        self._session.add(product)
        return product

    async def delete(self, user_id: uuid.UUID, product_id: uuid.UUID) -> int:
        _check_user_id(user_id)
        await self.delete_reminders(user_id, [product_id])
        result = await self._session.execute(
            delete(Product).where(Product.id == product_id, Product.user_id == user_id)
        )
        return result.rowcount or 0

    async def of_transaction(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> list[Product]:
        _check_user_id(user_id)
        statement = (
            select(Product)
            .where(Product.user_id == user_id, Product.transaction_id == transaction_id)
            .order_by(Product.created_at)
        )
        return list((await self._session.execute(statement)).scalars())

    async def warranty(self, product_id: uuid.UUID) -> Warranty | None:
        """Only call with a product already checked to be the user's."""
        statement = select(Warranty).where(Warranty.product_id == product_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def return_window(self, product_id: uuid.UUID) -> ReturnWindow | None:
        """Only call with a product already checked to be the user's."""
        statement = select(ReturnWindow).where(ReturnWindow.product_id == product_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add_any(self, row: object) -> None:
        self._session.add(row)

    async def close_expired_windows(self, today: date, user_id: uuid.UUID | None = None) -> int:
        """OPEN -> CLOSED once the end date is over. `user_id` None: everyone (start-up job)."""
        statement = update(ReturnWindow).where(
            ReturnWindow.status == ReturnWindowStatus.OPEN, ReturnWindow.end_date < today
        )
        if user_id is not None:
            _check_user_id(user_id)
            statement = statement.where(
                ReturnWindow.product_id.in_(select(Product.id).where(Product.user_id == user_id))
            )
        result = await self._session.execute(statement.values(status=ReturnWindowStatus.CLOSED))
        return result.rowcount or 0

    async def delete_reminders(self, user_id: uuid.UUID, product_ids: Iterable[uuid.UUID]) -> None:
        """The warranty / return reminders of these products that were not delivered yet (P13
        creates them with the product id as target)."""
        _check_user_id(user_id)
        ids = list(product_ids)
        if not ids:
            return
        await self._session.execute(
            delete(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.type.in_(PRODUCT_REMINDERS),
                Reminder.target_id.in_(ids),
                Reminder.delivered_at.is_(None),
            )
        )

    async def documents(
        self, user_id: uuid.UUID, product_id: uuid.UUID, transaction_id: uuid.UUID | None
    ) -> list[Document]:
        _check_user_id(user_id)
        owner = Document.product_id == product_id
        if transaction_id is not None:
            owner = owner | (Document.transaction_id == transaction_id)
        statement = (
            select(Document).where(Document.user_id == user_id, owner).order_by(Document.created_at)
        )
        return list((await self._session.execute(statement)).scalars())

    # ---- suggestions (spec 10.1) ------------------------------------------------------------

    async def suggestions(
        self,
        user_id: uuid.UUID,
        *,
        min_minor: int,
        categories: Sequence[CategoryKey],
        transaction_id: uuid.UUID | None = None,
    ) -> list[SuggestionRow]:
        """Receipt lines from `min_minor`, and purchases from `min_minor` that have no such line,
        in the given categories; without a product yet, not dismissed. Newest first."""
        _check_user_id(user_id)
        base = [
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.kind == TransactionKind.PURCHASE,
            Transaction.is_estimated.is_(False),
            Category.key.in_(categories),
        ]
        if transaction_id is not None:
            base.append(Transaction.id == transaction_id)
        has_product_tx = exists().where(
            Product.user_id == user_id, Product.transaction_id == Transaction.id
        )
        dismissed_tx = exists().where(
            ProductSuggestionDismissal.user_id == user_id,
            ProductSuggestionDismissal.transaction_id == Transaction.id,
            ProductSuggestionDismissal.receipt_item_id.is_(None),
        )
        big_item = and_(
            ReceiptItem.observation_id.in_(
                select(Observation.id).where(
                    Observation.user_id == user_id,
                    Observation.transaction_id == Transaction.id,
                    Observation.status == ObservationStatus.CONFIRMED,
                )
            ),
            ReceiptItem.total_price_minor >= min_minor,
        )
        items = (
            select(
                Transaction.id,
                ReceiptItem.id,
                ReceiptItem.name_raw,
                Transaction.merchant_display,
                Category.key,
                Transaction.purchase_date,
                ReceiptItem.total_price_minor,
            )
            .join(Category, Category.id == Transaction.category_id)
            .join(ReceiptItem, big_item)
            .where(
                *base,
                ~exists().where(
                    Product.user_id == user_id, Product.receipt_item_id == ReceiptItem.id
                ),
                ~exists().where(
                    ProductSuggestionDismissal.user_id == user_id,
                    ProductSuggestionDismissal.receipt_item_id == ReceiptItem.id,
                ),
                ~dismissed_tx,
                ~has_product_tx,
            )
        )
        # Joined flat so that it correlates to the outer purchase: a nested IN (...) inside
        # EXISTS left `transactions` uncorrelated and one big line anywhere hid every purchase.
        has_big_item = (
            select(ReceiptItem.id)
            .join(Observation, Observation.id == ReceiptItem.observation_id)
            .where(
                Observation.user_id == user_id,
                Observation.transaction_id == Transaction.id,
                Observation.status == ObservationStatus.CONFIRMED,
                ReceiptItem.total_price_minor >= min_minor,
            )
            .exists()
        )
        purchases = (
            select(
                Transaction.id,
                Transaction.merchant_display,
                Transaction.merchant_display,
                Category.key,
                Transaction.purchase_date,
                Transaction.total_minor,
            )
            .join(Category, Category.id == Transaction.category_id)
            .where(
                *base,
                Transaction.total_minor >= min_minor,
                ~has_big_item,
                ~has_product_tx,
                ~dismissed_tx,
            )
        )
        result = [
            SuggestionRow(t_id, item_id, name, merchant, CategoryKey(key), day, int(price))
            for t_id, item_id, name, merchant, key, day, price in (
                await self._session.execute(items)
            ).all()
        ]
        result += [
            SuggestionRow(t_id, None, name, merchant, CategoryKey(key), day, int(price))
            for t_id, name, merchant, key, day, price in (
                await self._session.execute(purchases)
            ).all()
        ]
        result.sort(key=lambda s: (s.purchase_date, s.price_minor), reverse=True)
        return result

    async def dismissed(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, receipt_item_id: uuid.UUID | None
    ) -> bool:
        _check_user_id(user_id)
        item = (
            ProductSuggestionDismissal.receipt_item_id.is_(None)
            if receipt_item_id is None
            else ProductSuggestionDismissal.receipt_item_id == receipt_item_id
        )
        statement = select(ProductSuggestionDismissal.id).where(
            ProductSuggestionDismissal.user_id == user_id,
            ProductSuggestionDismissal.transaction_id == transaction_id,
            item,
        )
        return (await self._session.execute(statement)).first() is not None

    def add_dismissal(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, receipt_item_id: uuid.UUID | None
    ) -> None:
        _check_user_id(user_id)
        self._session.add(
            ProductSuggestionDismissal(
                user_id=user_id, transaction_id=transaction_id, receipt_item_id=receipt_item_id
            )
        )

    async def receipt_item(
        self, user_id: uuid.UUID, receipt_item_id: uuid.UUID
    ) -> tuple[ReceiptItem, uuid.UUID] | None:
        """A line of one of the user's confirmed receipts, with its purchase id."""
        _check_user_id(user_id)
        statement = (
            select(ReceiptItem, Observation.transaction_id)
            .join(Observation, Observation.id == ReceiptItem.observation_id)
            .where(
                ReceiptItem.id == receipt_item_id,
                Observation.user_id == user_id,
                Observation.transaction_id.is_not(None),
            )
        )
        found = (await self._session.execute(statement)).first()
        return (found[0], found[1]) if found else None

    # ---- refunds ------------------------------------------------------------------------------

    async def refunded(
        self, user_id: uuid.UUID, transaction_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Purchase id -> sum of its (not deleted) refunds."""
        _check_user_id(user_id)
        if not transaction_ids:
            return {}
        statement = (
            select(Transaction.refund_of_id, func.sum(Transaction.total_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.REFUND,
                Transaction.deleted_at.is_(None),
                Transaction.refund_of_id.in_(transaction_ids),
            )
            .group_by(Transaction.refund_of_id)
        )
        return {row[0]: int(row[1]) for row in await self._session.execute(statement)}

    async def refunds_of(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> list[Transaction]:
        _check_user_id(user_id)
        statement = (
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.REFUND,
                Transaction.deleted_at.is_(None),
                Transaction.refund_of_id == transaction_id,
            )
            .order_by(Transaction.purchase_date, Transaction.created_at)
        )
        return list((await self._session.execute(statement)).scalars())
