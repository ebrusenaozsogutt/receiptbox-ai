"""Products, warranties and return windows (spec 10, P12).

- A product is created from a purchase, from one line of its receipt, or by hand. Empty fields are
  filled from the purchase / line.
- On creation the defaults of `product_defaults` are proposed WITH their source: a warranty of
  2 years (`LEGAL_DEFAULT`, unconfirmed) when the purchase date is known; a return window of
  14 days (`LEGAL_DEFAULT`) for an ONLINE purchase only. Nothing is invented for an in-store or
  unknown channel: the user enters the store's period.
- A source label must be true: `LEGAL_DEFAULT` is accepted only for the default date itself.
- A return window is CLOSED once its end is over (at start-up and whenever products are read).
- Suggestions (spec 10.1): purchases or receipt lines from PRODUCT_SUGGEST_MIN_MINOR in TECHNOLOGY,
  HOME or CLOTHING without a product; "bir daha sorma" is stored per purchase / line.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationFailedError
from app.models import Category, InstallmentPlan, ReturnWindow, Transaction, Warranty
from app.models.enums import (
    CategoryKey,
    Channel,
    InstallmentPlanStatus,
    ProductStatus,
    ReturnWindowSource,
    ReturnWindowStatus,
    WarrantySource,
)
from app.repositories.products import ProductRepository, ProductRow
from app.schemas.documents import DocumentOut
from app.schemas.products import (
    DismissIn,
    ProductDetail,
    ProductIn,
    ProductList,
    ProductOut,
    ProductPatch,
    ProductSuggestionList,
    ProductSuggestionOut,
    ReturnWindowIn,
    ReturnWindowOut,
    WarrantyIn,
    WarrantyOut,
)
from app.services.extraction_service import BUSINESS_TIMEZONE
from app.services.product_defaults import days_left, default_return_end, default_warranty_end
from app.services.refund_service import RefundService
from app.services.reminder_service import ReminderService

SUGGESTED_CATEGORIES = (CategoryKey.TECHNOLOGY, CategoryKey.HOME, CategoryKey.CLOTHING)
RETURN_ATTENTION_DAYS = 7
WARRANTY_ATTENTION_DAYS = 30


def _today() -> date:
    return datetime.now(BUSINESS_TIMEZONE).date()


def warranty_out(warranty: Warranty | None, today: date) -> WarrantyOut | None:
    if warranty is None:
        return None
    return WarrantyOut(
        start_date=warranty.start_date,
        end_date=warranty.end_date,
        source=warranty.source,
        confirmed=warranty.confirmed,
        days_left=days_left(warranty.end_date, today),
    )


def return_out(window: ReturnWindow | None, today: date) -> ReturnWindowOut | None:
    if window is None:
        return None
    return ReturnWindowOut(
        end_date=window.end_date,
        source=window.source,
        status=window.status,
        days_left=days_left(window.end_date, today),
    )


def product_out(row: ProductRow, today: date) -> ProductOut:
    p = row.product
    return ProductOut(
        id=p.id,
        transaction_id=p.transaction_id,
        receipt_item_id=p.receipt_item_id,
        name=p.name,
        brand=p.brand,
        model=p.model,
        serial_number=p.serial_number,
        category_key=CategoryKey(p.product_category) if p.product_category else None,
        purchase_date=p.purchase_date,
        purchase_price_minor=p.purchase_price_minor,
        status=p.status,
        merchant_display=row.merchant_display,
        channel=row.channel,
        warranty=warranty_out(row.warranty, today),
        return_window=return_out(row.return_window, today),
        document_count=row.document_count,
    )


class ProductService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        today: Callable[[], date] = _today,
    ) -> None:
        self._session = session
        self._settings = settings
        self._repo = ProductRepository(session)
        self._refunds = RefundService(session)
        self.today = today

    # ---- reads ----------------------------------------------------------------------------------

    async def _commit(self, user_id: uuid.UUID) -> None:
        """Commit a change to a product, its warranty or return window, after recomputing the
        deadline reminders in the same transaction (P13)."""
        await ReminderService(self._session).sync(user_id)
        await self._session.commit()

    async def products(
        self, user_id: uuid.UUID, statuses: list[ProductStatus] | None = None
    ) -> ProductList:
        await self._repo.close_expired_windows(self.today(), user_id)
        await self._session.commit()
        today = self.today()
        return ProductList(
            items=[product_out(r, today) for r in await self._repo.rows(user_id, statuses=statuses)]
        )

    async def detail(self, user_id: uuid.UUID, product_id: uuid.UUID) -> ProductDetail:
        await self._repo.close_expired_windows(self.today(), user_id)
        await self._session.commit()
        row = await self._repo.row(user_id, product_id)
        if row is None:
            raise NotFoundError()
        base = product_out(row, self.today())
        transaction_id = row.product.transaction_id if row.merchant_display is not None else None
        financing: int | None = None
        refundable: int | None = None
        if transaction_id is not None:
            purchase = await self._refunds.purchase(user_id, transaction_id)
            refundable = await self._refunds.refundable(user_id, purchase)
            plan = (
                await self._session.execute(
                    select(InstallmentPlan).where(
                        InstallmentPlan.transaction_id == transaction_id,
                        InstallmentPlan.status != InstallmentPlanStatus.CANCELLED,
                    )
                )
            ).scalar_one_or_none()
            if plan is not None and plan.total_payable_minor > purchase.total_minor:
                financing = plan.total_payable_minor - purchase.total_minor
        documents = await self._repo.documents(user_id, product_id, transaction_id)
        return ProductDetail(
            **base.model_dump(),
            financing_cost_minor=financing,
            refundable_minor=refundable,
            documents=[DocumentOut.model_validate(d) for d in documents],
        )

    # ---- create, change, delete -----------------------------------------------------------------

    async def create(self, user_id: uuid.UUID, body: ProductIn) -> ProductDetail:
        transaction_id = body.transaction_id
        item_name: str | None = None
        item_price: int | None = None
        if body.receipt_item_id is not None:
            found = await self._repo.receipt_item(user_id, body.receipt_item_id)
            if found is None:
                raise NotFoundError()
            item, item_transaction = found
            if transaction_id is not None and transaction_id != item_transaction:
                raise ValidationFailedError("The receipt line belongs to another purchase.")
            transaction_id = item_transaction
            item_name, item_price = item.name_raw, item.total_price_minor
        purchase: Transaction | None = None
        category: CategoryKey | None = None
        if transaction_id is not None:
            purchase = await self._refunds.purchase(user_id, transaction_id)
            category = await self._category_key(purchase.category_id)
        name = (body.name or item_name or (purchase.merchant_display if purchase else "")).strip()
        if not name:
            raise ValidationFailedError("A product needs a name.")
        purchase_date = body.purchase_date or (purchase.purchase_date if purchase else None)
        price = body.purchase_price_minor
        if price is None:
            price = (
                item_price
                if item_price is not None
                else (purchase.total_minor if purchase else None)
            )
        channel = purchase.channel if purchase else (body.channel or Channel.UNKNOWN)
        product = self._repo.add(
            user_id,
            transaction_id=transaction_id,
            receipt_item_id=body.receipt_item_id,
            name=name[:200],
            brand=body.brand,
            model=body.model,
            serial_number=body.serial_number,
            product_category=(body.category_key or category).value
            if (body.category_key or category)
            else None,
            purchase_date=purchase_date,
            purchase_price_minor=price,
            status=ProductStatus.ACTIVE,
        )
        await self._session.flush()
        today = self.today()
        if purchase_date is not None:
            self._repo.add_any(
                Warranty(
                    product_id=product.id,
                    start_date=purchase_date,
                    end_date=default_warranty_end(purchase_date),
                    source=WarrantySource.LEGAL_DEFAULT,
                    confirmed=False,
                )
            )
            return_end = default_return_end(purchase_date, channel)
            if return_end is not None:
                self._repo.add_any(
                    ReturnWindow(
                        product_id=product.id,
                        end_date=return_end,
                        source=ReturnWindowSource.LEGAL_DEFAULT,
                        status=ReturnWindowStatus.OPEN
                        if return_end >= today
                        else ReturnWindowStatus.CLOSED,
                    )
                )
        await self._commit(user_id)
        return await self.detail(user_id, product.id)

    async def patch(
        self, user_id: uuid.UUID, product_id: uuid.UUID, body: ProductPatch
    ) -> ProductDetail:
        product = await self._repo.get(user_id, product_id)
        if product is None:
            raise NotFoundError()
        fields = body.model_dump(exclude_unset=True)
        status = fields.pop("status", None)
        if "category_key" in fields:
            key = fields.pop("category_key")
            product.product_category = key.value if key else None
        if "name" in fields and fields["name"] is None:
            fields.pop("name")
        for name, value in fields.items():
            setattr(product, name, value)
        if status is not None and status != product.status:
            if status == ProductStatus.RETURNED:
                if product.transaction_id is not None:
                    raise ValidationFailedError("Record the refund of the purchase instead.")
                await self._refunds.mark_returned(user_id, [product])
            else:
                product.status = status
                if status == ProductStatus.ARCHIVED:
                    await self._repo.delete_reminders(user_id, [product.id])
        await self._commit(user_id)
        return await self.detail(user_id, product_id)

    async def delete(self, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
        if await self._repo.delete(user_id, product_id) == 0:
            raise NotFoundError()
        await self._commit(user_id)

    async def put_warranty(
        self, user_id: uuid.UUID, product_id: uuid.UUID, body: WarrantyIn
    ) -> ProductDetail:
        product = await self._repo.get(user_id, product_id)
        if product is None:
            raise NotFoundError()
        if body.start_date is not None and body.start_date > body.end_date:
            raise ValidationFailedError("The warranty cannot end before it starts.")
        if body.source == WarrantySource.LEGAL_DEFAULT and (
            product.purchase_date is None
            or body.end_date != default_warranty_end(product.purchase_date)
        ):
            raise ValidationFailedError("LEGAL_DEFAULT is only the 2-year default itself.")
        warranty = await self._repo.warranty(product.id)
        if warranty is None:
            warranty = Warranty(product_id=product.id, end_date=body.end_date, source=body.source)
            self._repo.add_any(warranty)
        warranty.start_date = body.start_date or product.purchase_date
        warranty.end_date = body.end_date
        warranty.source = body.source
        warranty.confirmed = body.confirmed
        await self._commit(user_id)
        return await self.detail(user_id, product_id)

    async def put_return_window(
        self, user_id: uuid.UUID, product_id: uuid.UUID, body: ReturnWindowIn
    ) -> ProductDetail:
        row = await self._repo.row(user_id, product_id)
        if row is None:
            raise NotFoundError()
        product = row.product
        if body.source == ReturnWindowSource.LEGAL_DEFAULT and (
            product.purchase_date is None
            or body.end_date
            != default_return_end(product.purchase_date, row.channel or Channel.UNKNOWN)
        ):
            raise ValidationFailedError(
                "LEGAL_DEFAULT is only the 14-day default of an online purchase."
            )
        if product.purchase_date is not None and body.end_date < product.purchase_date:
            raise ValidationFailedError("The return window cannot end before the purchase.")
        window = await self._repo.return_window(product.id)
        if window is None:
            window = ReturnWindow(product_id=product.id, end_date=body.end_date, source=body.source)
            self._repo.add_any(window)
        window.end_date = body.end_date
        window.source = body.source
        if product.status == ProductStatus.RETURNED:
            window.status = ReturnWindowStatus.RETURNED
        else:
            window.status = (
                ReturnWindowStatus.OPEN
                if body.end_date >= self.today()
                else ReturnWindowStatus.CLOSED
            )
        await self._commit(user_id)
        return await self.detail(user_id, product_id)

    # ---- suggestions (spec 10.1) --------------------------------------------------------------

    async def suggestions(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID | None = None
    ) -> ProductSuggestionList:
        rows = await self._repo.suggestions(
            user_id,
            min_minor=self._settings.product_suggest_min_minor,
            categories=SUGGESTED_CATEGORIES,
            transaction_id=transaction_id,
        )
        return ProductSuggestionList(
            items=[
                ProductSuggestionOut(
                    transaction_id=r.transaction_id,
                    receipt_item_id=r.receipt_item_id,
                    name=r.name,
                    merchant_display=r.merchant_display,
                    category_key=r.category_key,
                    purchase_date=r.purchase_date,
                    price_minor=r.price_minor,
                )
                for r in rows
            ]
        )

    async def dismiss(self, user_id: uuid.UUID, body: DismissIn) -> None:
        """ "Hayır, bir daha sorma" for a purchase or one line of its receipt."""
        await self._refunds.purchase(user_id, body.transaction_id)  # 404 if not the user's
        if body.receipt_item_id is not None:
            found = await self._repo.receipt_item(user_id, body.receipt_item_id)
            if found is None or found[1] != body.transaction_id:
                raise NotFoundError()
        if not await self._repo.dismissed(user_id, body.transaction_id, body.receipt_item_id):
            self._repo.add_dismissal(user_id, body.transaction_id, body.receipt_item_id)
        await self._session.commit()

    # ---- home: "Dikkat gerektirenler" -------------------------------------------------------

    async def attention(self, user_id: uuid.UUID) -> list[ProductOut]:
        """Active products whose return window ends within 7 days or whose warranty ends within
        30 days (today included), soonest first."""
        today = self.today()
        await self._repo.close_expired_windows(today, user_id)
        result = []
        for row in await self._repo.rows(user_id, statuses=[ProductStatus.ACTIVE]):
            window, warranty = row.return_window, row.warranty
            if (
                window is not None
                and window.status == ReturnWindowStatus.OPEN
                and 0 <= days_left(window.end_date, today) <= RETURN_ATTENTION_DAYS
            ) or (
                warranty is not None
                and 0 <= days_left(warranty.end_date, today) <= WARRANTY_ATTENTION_DAYS
            ):
                result.append(product_out(row, today))
        return result

    async def _category_key(self, category_id: uuid.UUID | None) -> CategoryKey | None:
        if category_id is None:
            return None
        key = (
            await self._session.execute(select(Category.key).where(Category.id == category_id))
        ).scalar_one_or_none()
        return CategoryKey(key) if key else None
