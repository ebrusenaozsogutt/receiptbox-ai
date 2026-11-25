"""A seeded, made-up dataset for the P11 analytics tests and the Python reference calculation the
SQL of `app/services/analytics.py` is compared with.

The data deliberately contains everything that must NOT be counted twice or at all: merged
purchases (two confirmed observations on one purchase, plus a bank row that is an installment
payment), installment plans (also a cancelled one and an estimated purchase), refunds of a
purchase (also in a later month, of a deleted purchase, and one without an original), deleted
purchases, purchases without a category or merchant, pending observations that are not purchases
yet, and the purchases of a second user.

The reference implementation below is plain Python over the generated objects, written from the
spec 6.3 rules, not from the SQL.
"""

import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Merchant, Observation, Transaction, User
from app.models.enums import (
    CategoryKey,
    InstallmentPaymentStatus,
    InstallmentPlanStatus,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    TransactionKind,
)
from app.models.installment import InstallmentPayment, InstallmentPlan
from app.services.installment_schedule import add_months, first_of_month, split_total

FIRST_DAY = date(2025, 11, 1)
LAST_DAY = date(2026, 12, 31)


@dataclass
class Tx:
    id: uuid.UUID
    user_id: uuid.UUID
    day: date
    category: CategoryKey | None
    merchant: str  # what the spending is grouped by: canonical name, else the display name
    total: int
    kind: TransactionKind = TransactionKind.PURCHASE
    refund_of: uuid.UUID | None = None
    deleted: bool = False


@dataclass
class Payment:
    transaction_id: uuid.UUID
    due_month: date
    amount: int
    cancelled: bool


@dataclass
class Dataset:
    user: User
    other: User
    transactions: list[Tx] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)

    def mine(self) -> list[Tx]:
        return [t for t in self.transactions if t.user_id == self.user.id]


async def _user(session: AsyncSession, label: str) -> User:
    user = User(email=f"{label}-{uuid.uuid4().hex[:8]}@example.test", password_hash="not-a-hash")
    session.add(user)
    await session.flush()
    return user


def _random_day(rng: random.Random) -> date:
    return FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))


async def build(
    session: AsyncSession, *, purchases: int = 230, seed: int = 11, user: User | None = None
) -> Dataset:
    """Insert the dataset (in the caller's transaction) and return what was inserted. `user`: the
    main user (default: a new one)."""
    rng = random.Random(seed)
    categories = {c.key: c.id for c in (await session.execute(select(Category))).scalars()}
    merchants = list(
        (await session.execute(select(Merchant).order_by(Merchant.canonical_name).limit(12)))
        .scalars()
        .all()
    )
    data = Dataset(
        user=user or await _user(session, "analytics"), other=await _user(session, "other")
    )
    free_names = ["ORNEK BAKKAL", "Örnek Kafe", "PAZAR YERI", "Kırtasiye Ali"]

    async def add_tx(user: User, **values: object) -> Tx:
        merchant: Merchant | None = values.pop("merchant_obj", None)  # type: ignore[assignment]
        display = merchant.canonical_name.upper() if merchant else str(values.pop("display"))
        category: CategoryKey | None = values.pop("category")  # type: ignore[assignment]
        row = Transaction(
            user_id=user.id,
            merchant_id=merchant.id if merchant else None,
            merchant_display=display,
            category_id=categories[category] if category else None,
            **values,
        )
        session.add(row)
        await session.flush()
        tx = Tx(
            id=row.id,
            user_id=user.id,
            day=row.purchase_date,
            category=category,
            merchant=merchant.canonical_name if merchant else display,
            total=row.total_minor,
            kind=row.kind,
            refund_of=row.refund_of_id,
            deleted=row.deleted_at is not None,
        )
        data.transactions.append(tx)
        return tx

    def observation(user: User, tx_id: uuid.UUID | None, source: ObservationSource, **kw) -> None:  # noqa: ANN003
        session.add(
            Observation(
                user_id=user.id,
                source=source,
                status=kw.pop("status", ObservationStatus.CONFIRMED),
                transaction_id=tx_id,
                amount_minor=kw.pop("amount", 1000),
                obs_date=kw.pop("day", None),
                fingerprint=uuid.uuid4().hex,
                **kw,
            )
        )

    all_keys = list(CategoryKey)
    made: list[Tx] = []
    for index in range(purchases):
        user = data.user if index % 9 else data.other  # every 9th purchase is another user's
        merchant = rng.choice(merchants) if merchants and rng.random() < 0.7 else None
        values: dict[str, object] = {
            "purchase_date": _random_day(rng),
            "total_minor": rng.randrange(100, 600_000),
            "category": None if rng.random() < 0.08 else rng.choice(all_keys),
            "kind": TransactionKind.PURCHASE,
        }
        if merchant is not None:
            values["merchant_obj"] = merchant
        else:
            values["display"] = rng.choice(free_names)
        if rng.random() < 0.05:
            values["deleted_at"] = datetime(2026, 11, 20, tzinfo=UTC)
        estimated = rng.random() < 0.03
        if estimated:
            values["is_estimated"] = True
        tx = await add_tx(user, **values)
        made.append(tx)
        # merged: a receipt and a bank row on the same purchase (evidence, never summed)
        if rng.random() < 0.25:
            observation(user, tx.id, ObservationSource.RECEIPT, amount=tx.total, day=tx.day)
            observation(user, tx.id, ObservationSource.BANK_SCREENSHOT, amount=tx.total, day=tx.day)
        # installments: a plan with its payments (one in ten is cancelled)
        if tx.kind == TransactionKind.PURCHASE and (estimated or rng.random() < 0.15):
            count = rng.choice([2, 3, 6, 9, 12])
            cancelled = rng.random() < 0.1
            first_due = add_months(first_of_month(tx.day), 1)
            plan = InstallmentPlan(
                transaction_id=tx.id,
                count=count,
                installment_minor=split_total(tx.total, count)[0],
                total_payable_minor=tx.total,
                first_due_month=first_due,
                status=InstallmentPlanStatus.CANCELLED
                if cancelled
                else InstallmentPlanStatus.ACTIVE,
            )
            session.add(plan)
            await session.flush()
            row_ts = await session.get(Transaction, tx.id)
            assert row_ts is not None
            row_ts.payment_type = PaymentType.INSTALLMENT
            for seq, amount in enumerate(split_total(tx.total, count), start=1):
                payment = InstallmentPayment(
                    plan_id=plan.id,
                    seq=seq,
                    due_month=add_months(first_due, seq - 1),
                    amount_minor=amount,
                    status=InstallmentPaymentStatus.OBSERVED
                    if seq == 1
                    else InstallmentPaymentStatus.EXPECTED,
                )
                session.add(payment)
                await session.flush()
                if seq == 1:  # the bank row of payment 1: evidence, not spending
                    observation(
                        user,
                        tx.id,
                        ObservationSource.BANK_SCREENSHOT,
                        amount=amount,
                        day=payment.due_month,
                        installment_payment_id=payment.id,
                        installment_seq=1,
                        installment_count=count,
                    )
                # a payment of a deleted purchase is not due any more
                data.payments.append(
                    Payment(tx.id, payment.due_month, amount, cancelled or tx.deleted)
                )
    # pending observations: not purchases yet, never counted
    for _ in range(15):
        observation(
            data.user,
            None,
            ObservationSource.BANK_SCREENSHOT,
            status=ObservationStatus.PENDING_REVIEW,
            amount=rng.randrange(100, 50_000),
            day=_random_day(rng),
        )
    # refunds: of a purchase (often in a later month), of a deleted purchase, without an original
    originals = [t for t in made if t.kind == TransactionKind.PURCHASE]
    for index in range(30):
        original = rng.choice(originals)
        owner = data.user if original.user_id == data.user.id else data.other
        later = original.day + timedelta(days=rng.randrange(0, 60))
        await add_tx(
            owner,
            display="IADE",
            category=None,
            purchase_date=later,
            total_minor=max(1, original.total // rng.choice([1, 2, 4])),
            kind=TransactionKind.REFUND,
            refund_of_id=original.id,
            deleted_at=datetime(2026, 11, 20, tzinfo=UTC) if index == 0 else None,
        )
    for _ in range(3):
        await add_tx(
            data.user,
            display="IADE MAGAZA",
            category=rng.choice(all_keys),
            purchase_date=_random_day(rng),
            total_minor=rng.randrange(100, 20_000),
            kind=TransactionKind.REFUND,
        )
    await session.flush()
    return data


# ---- the reference calculation -----------------------------------------------------------------


def lines(data: Dataset) -> list[tuple[date, CategoryKey, str, int]]:
    """(day, category, merchant, signed amount) per amount that counts, by the spec 6.3 rules."""
    by_id = {t.id: t for t in data.mine()}
    result = []
    for t in data.mine():
        if t.deleted:
            continue
        if t.kind == TransactionKind.PURCHASE:
            result.append((t.day, t.category or CategoryKey.OTHER, t.merchant, t.total))
        elif t.refund_of is None:
            result.append((t.day, t.category or CategoryKey.OTHER, t.merchant, -t.total))
        else:
            original = by_id.get(t.refund_of)
            if original is None or original.deleted or original.kind != TransactionKind.PURCHASE:
                continue
            result.append(
                (original.day, original.category or CategoryKey.OTHER, original.merchant, -t.total)
            )
    return result


def total(data: Dataset, start: date, end: date) -> int:
    return sum(amount for day, _, _, amount in lines(data) if start <= day <= end)


def grouped(data: Dataset, start: date, end: date, by: str) -> dict[str, int]:
    sums: dict[str, int] = defaultdict(int)
    for day, category, merchant, amount in lines(data):
        if not start <= day <= end:
            continue
        if by == "category":
            key = category.value
        elif by == "merchant":
            key = merchant
        elif by == "month":
            key = f"{day.year:04d}-{day.month:02d}"
        else:  # ISO week
            iso = day.isocalendar()
            key = f"{iso.year:04d}-W{iso.week:02d}"
        sums[key] += amount
    if by in ("category", "merchant"):
        return {k: v for k, v in sums.items() if v != 0}
    return dict(sums)


def payments_due(data: Dataset, month: date) -> int:
    return sum(
        p.amount
        for p in data.payments
        if not p.cancelled
        and p.due_month == month
        and any(t.id == p.transaction_id and t.user_id == data.user.id for t in data.transactions)
    )
