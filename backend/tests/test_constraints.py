"""Database-level rules: CHECKs, uniques, cascades and defaults (not just Python validation)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Budget,
    Category,
    InstallmentPayment,
    InstallmentPlan,
    Merchant,
    MerchantAlias,
    Observation,
    Product,
    Transaction,
    User,
    UserCategoryRule,
    Warranty,
)
from app.models.enums import (
    CategoryKey,
    Channel,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    TransactionKind,
    WarrantySource,
)
from tests.conftest import create_user

TODAY = date(2026, 11, 16)


def _transaction(user: User, total_minor: int = 49460, **overrides: object) -> Transaction:
    values: dict[str, object] = {
        "user_id": user.id,
        "merchant_display": "MIGROS",
        "purchase_date": TODAY,
        "total_minor": total_minor,
    }
    return Transaction(**{**values, **overrides})


def _observation(user: User, transaction: Transaction | None = None, **overrides: object):
    values: dict[str, object] = {
        "user_id": user.id,
        "transaction_id": transaction.id if transaction else None,
        "source": ObservationSource.RECEIPT,
        "status": ObservationStatus.CONFIRMED,
        "fingerprint": uuid.uuid4().hex,
    }
    return Observation(**{**values, **overrides})


async def _rejected(session: AsyncSession, *objects: object) -> None:
    """Assert that the database refuses these rows (rolls back only a savepoint)."""
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add_all(objects)


async def _count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ---- defaults ----------------------------------------------------------------------------


async def test_minimal_transaction_gets_the_documented_defaults(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user)
    db_session.add(transaction)
    await db_session.flush()
    await db_session.refresh(transaction)

    assert isinstance(transaction.id, uuid.UUID)  # gen_random_uuid() on the server
    assert transaction.currency == "TRY"
    assert transaction.payment_type == PaymentType.SINGLE
    assert transaction.channel == Channel.UNKNOWN
    assert transaction.kind == TransactionKind.PURCHASE
    assert transaction.is_estimated is False
    assert transaction.created_at is not None
    assert transaction.updated_at is not None
    assert transaction.deleted_at is None


# ---- money is never negative ---------------------------------------------------------------


async def test_negative_transaction_total_is_rejected(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    await _rejected(db_session, _transaction(user, total_minor=-1))


async def test_zero_total_is_allowed(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    db_session.add(_transaction(user, total_minor=0))

    await db_session.flush()  # no error


async def test_negative_observation_amount_is_rejected_but_unknown_amount_is_allowed(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)

    await _rejected(db_session, _observation(user, amount_minor=-5))

    unknown = _observation(user, amount_minor=None)  # "could not read the amount"
    db_session.add(unknown)
    await db_session.flush()
    assert unknown.amount_minor is None


async def test_negative_budget_and_product_price_are_rejected(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    category_id = (
        await db_session.execute(select(Category.id).where(Category.key == CategoryKey.OTHER))
    ).scalar_one()

    await _rejected(
        db_session, Budget(user_id=user.id, category_id=category_id, monthly_limit_minor=-100)
    )
    await _rejected(db_session, Product(user_id=user.id, name="TV", purchase_price_minor=-1))


# ---- enums and e-mail ----------------------------------------------------------------------


async def test_database_rejects_unknown_enum_values(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO transactions (user_id, merchant_display, purchase_date, "
                    "total_minor, kind) VALUES (:user_id, 'X', current_date, 1, 'BOGUS')"
                ),
                {"user_id": user.id},
            )


async def test_email_must_be_lowercase(db_session: AsyncSession) -> None:
    await _rejected(db_session, User(email="Ebru@Example.test", password_hash="x"))


async def test_email_must_be_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="same@example.test", password_hash="x"))
    await db_session.flush()

    await _rejected(db_session, User(email="same@example.test", password_hash="x"))


# ---- merchant aliases (NULL user_id = global) ------------------------------------------------


async def _merchant(session: AsyncSession, name: str) -> Merchant:
    merchant = Merchant(canonical_name=f"{name}-{uuid.uuid4().hex[:6]}")
    session.add(merchant)
    await session.flush()
    return merchant


async def test_global_alias_cannot_be_added_twice(db_session: AsyncSession) -> None:
    merchant = await _merchant(db_session, "Test Merchant")
    alias = f"TEST ALIAS {uuid.uuid4().hex[:6]}".upper()
    db_session.add(MerchantAlias(merchant_id=merchant.id, alias_normalized=alias))
    await db_session.flush()

    # Plain UNIQUE would let this through, because NULL != NULL. NULLS NOT DISTINCT stops it.
    await _rejected(db_session, MerchantAlias(merchant_id=merchant.id, alias_normalized=alias))


async def test_user_alias_may_shadow_a_global_one_but_not_repeat(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    merchant = await _merchant(db_session, "Test Merchant")
    alias = f"TEST ALIAS {uuid.uuid4().hex[:6]}".upper()
    db_session.add(MerchantAlias(merchant_id=merchant.id, alias_normalized=alias))
    db_session.add(MerchantAlias(merchant_id=merchant.id, alias_normalized=alias, user_id=user.id))
    await db_session.flush()  # a user alias next to a global one is fine

    await _rejected(
        db_session,
        MerchantAlias(merchant_id=merchant.id, alias_normalized=alias, user_id=user.id),
    )


async def test_user_category_rule_primary_key_is_user_and_merchant(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    merchant = await _merchant(db_session, "Test Merchant")
    categories = (await db_session.execute(select(Category.id).limit(2))).scalars().all()
    db_session.add(
        UserCategoryRule(user_id=user.id, merchant_id=merchant.id, category_id=categories[0])
    )
    await db_session.flush()

    await _rejected(
        db_session,
        UserCategoryRule(user_id=user.id, merchant_id=merchant.id, category_id=categories[1]),
    )


# ---- "at most one CONFIRMED observation per source" (spec 6.3) -------------------------------


async def test_second_confirmed_observation_from_the_same_source_is_rejected(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user)
    db_session.add(transaction)
    await db_session.flush()
    db_session.add(_observation(user, transaction, source=ObservationSource.RECEIPT))
    await db_session.flush()

    await _rejected(db_session, _observation(user, transaction, source=ObservationSource.RECEIPT))


async def test_other_sources_and_non_confirmed_statuses_do_not_conflict(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user)
    db_session.add(transaction)
    await db_session.flush()

    db_session.add_all(
        [
            _observation(user, transaction, source=ObservationSource.RECEIPT),
            _observation(user, transaction, source=ObservationSource.BANK_SCREENSHOT),
            _observation(user, transaction, source=ObservationSource.EINVOICE_QR),
            # More RECEIPT rows are fine while they are not CONFIRMED:
            _observation(
                user,
                transaction,
                source=ObservationSource.RECEIPT,
                status=ObservationStatus.DUPLICATE,
            ),
            _observation(
                user,
                transaction,
                source=ObservationSource.RECEIPT,
                status=ObservationStatus.REJECTED,
            ),
        ]
    )
    await db_session.flush()  # no error


async def test_bank_rows_linked_through_installment_payments_are_exempt(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user, total_minor=300000, payment_type=PaymentType.INSTALLMENT)
    db_session.add(transaction)
    await db_session.flush()
    plan = InstallmentPlan(
        transaction_id=transaction.id,
        count=3,
        installment_minor=100000,
        total_payable_minor=300000,
        first_due_month=date(2026, 12, 1),
    )
    db_session.add(plan)
    await db_session.flush()
    payments = [
        InstallmentPayment(
            plan_id=plan.id, seq=seq, due_month=date(2027, seq, 1), amount_minor=100000
        )
        for seq in (1, 2)
    ]
    db_session.add_all(payments)
    await db_session.flush()

    # One bank row per monthly payment, all CONFIRMED, all BANK_SCREENSHOT, same transaction.
    db_session.add_all(
        [
            _observation(
                user,
                transaction,
                source=ObservationSource.BANK_SCREENSHOT,
                installment_payment_id=payment.id,
            )
            for payment in payments
        ]
    )
    await db_session.flush()  # no error


# ---- installments ----------------------------------------------------------------------------


async def _plan(session: AsyncSession, user: User) -> InstallmentPlan:
    transaction = _transaction(user, total_minor=300000)
    session.add(transaction)
    await session.flush()
    plan = InstallmentPlan(
        transaction_id=transaction.id,
        count=3,
        installment_minor=100000,
        total_payable_minor=300000,
        first_due_month=date(2026, 12, 1),
    )
    session.add(plan)
    await session.flush()
    return plan


async def test_installment_months_must_be_the_first_day(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    plan = await _plan(db_session, user)

    await _rejected(
        db_session,
        InstallmentPayment(plan_id=plan.id, seq=1, due_month=date(2026, 12, 15), amount_minor=1),
    )


async def test_installment_plan_first_due_month_must_be_the_first_day(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user)
    db_session.add(transaction)
    await db_session.flush()

    await _rejected(
        db_session,
        InstallmentPlan(
            transaction_id=transaction.id,
            count=3,
            installment_minor=1,
            total_payable_minor=3,
            first_due_month=date(2026, 12, 2),
        ),
    )


async def test_installment_sequence_numbers_are_unique_per_plan(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    plan = await _plan(db_session, user)
    db_session.add(
        InstallmentPayment(plan_id=plan.id, seq=1, due_month=date(2026, 12, 1), amount_minor=1)
    )
    await db_session.flush()

    await _rejected(
        db_session,
        InstallmentPayment(plan_id=plan.id, seq=1, due_month=date(2027, 1, 1), amount_minor=1),
    )


async def test_a_transaction_has_at_most_one_installment_plan(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    plan = await _plan(db_session, user)

    await _rejected(
        db_session,
        InstallmentPlan(
            transaction_id=plan.transaction_id,
            count=2,
            installment_minor=1,
            total_payable_minor=2,
            first_due_month=date(2027, 1, 1),
        ),
    )


# ---- warranties ------------------------------------------------------------------------------


async def test_warranty_cannot_start_after_it_ends_and_end_date_is_required(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    product = Product(user_id=user.id, name="Laptop")
    db_session.add(product)
    await db_session.flush()

    await _rejected(
        db_session,
        Warranty(
            product_id=product.id,
            start_date=date(2028, 1, 1),
            end_date=date(2027, 1, 1),
            source=WarrantySource.USER,
        ),
    )
    # An unknown start date stays empty (never invented); the end date is what matters.
    db_session.add(
        Warranty(product_id=product.id, end_date=date(2028, 11, 16), source=WarrantySource.USER)
    )
    await db_session.flush()


# ---- deletion rules --------------------------------------------------------------------------


async def test_deleting_a_user_removes_everything_they_own(db_session: AsyncSession) -> None:
    """Account deletion (spec 15.2): one DELETE on users cascades to all user-owned rows."""
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    for user in (alice, bob):
        transaction = _transaction(user)
        db_session.add(transaction)
        await db_session.flush()
        db_session.add(_observation(user, transaction))
        db_session.add(Product(user_id=user.id, name="Phone", transaction_id=transaction.id))
        await db_session.flush()

    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": alice.id})

    for model in (Transaction, Observation, Product):
        remaining = (
            await db_session.execute(select(model.user_id).where(model.user_id == alice.id))
        ).all()
        assert remaining == []
        assert await _count(db_session, model) >= 1  # Bob's rows are untouched


async def test_deleting_a_transaction_detaches_observations_and_keeps_products(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    transaction = _transaction(user)
    db_session.add(transaction)
    await db_session.flush()
    observation = _observation(user, transaction)
    product = Product(user_id=user.id, name="Phone", transaction_id=transaction.id)
    db_session.add_all([observation, product])
    await db_session.flush()

    await db_session.execute(
        text("DELETE FROM transactions WHERE id = :id"), {"id": transaction.id}
    )
    await db_session.refresh(observation)
    await db_session.refresh(product)

    assert observation.transaction_id is None  # becomes an "orphan" to re-link (spec 6.3)
    assert product.transaction_id is None  # the product itself stays
