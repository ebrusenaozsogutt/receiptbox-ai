"""Installment plans and payments. Both tables have no user_id: they are reached through their
purchase (`transactions.user_id`), and every query here joins it and filters by the caller."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InstallmentPayment, InstallmentPlan, Observation, Transaction
from app.models.enums import (
    InstallmentPaymentStatus,
    InstallmentPlanStatus,
    ObservationStatus,
    TransactionKind,
)
from app.repositories.base import _check_user_id


@dataclass(frozen=True)
class PlanRow:
    plan: InstallmentPlan
    payments: list[InstallmentPayment]
    transaction: Transaction
    linked_payment_ids: frozenset[uuid.UUID]  # payments that have a confirmed bank row


@dataclass(frozen=True)
class ScheduleRow:
    payment: InstallmentPayment
    plan: InstallmentPlan
    transaction: Transaction


class InstallmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- plans ----------------------------------------------------------------------------

    async def plan_of_transaction(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> InstallmentPlan | None:
        _check_user_id(user_id)
        statement = (
            select(InstallmentPlan)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                InstallmentPlan.transaction_id == transaction_id,
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def plan(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> InstallmentPlan | None:
        _check_user_id(user_id)
        statement = (
            select(InstallmentPlan)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                InstallmentPlan.id == plan_id,
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def payments(self, plan_id: uuid.UUID) -> list[InstallmentPayment]:
        """The plan's payments. Only call it with a plan that `plan()` or `plan_of_transaction()`
        returned for the user: it does not check the owner itself."""
        statement = (
            select(InstallmentPayment)
            .where(InstallmentPayment.plan_id == plan_id)
            .order_by(InstallmentPayment.seq)
        )
        return list((await self._session.execute(statement)).scalars().all())

    def add_plan(
        self,
        transaction_id: uuid.UUID,
        *,
        count: int,
        installment_minor: int,
        total_payable_minor: int,
        first_due_month: date,
    ) -> InstallmentPlan:
        plan = InstallmentPlan(
            transaction_id=transaction_id,
            count=count,
            installment_minor=installment_minor,
            total_payable_minor=total_payable_minor,
            first_due_month=first_due_month,
            status=InstallmentPlanStatus.ACTIVE,
        )
        self._session.add(plan)
        return plan

    def add_payment(
        self,
        plan_id: uuid.UUID,
        *,
        seq: int,
        due_month: date,
        amount_minor: int,
        status: InstallmentPaymentStatus,
    ) -> InstallmentPayment:
        payment = InstallmentPayment(
            plan_id=plan_id,
            seq=seq,
            due_month=due_month,
            amount_minor=amount_minor,
            status=status,
        )
        self._session.add(payment)
        return payment

    async def delete_plan(self, plan: InstallmentPlan) -> None:
        """Delete a plan and its payments (the caller checked that no bank row is attached)."""
        await self._session.execute(
            delete(InstallmentPayment).where(InstallmentPayment.plan_id == plan.id)
        )
        await self._session.delete(plan)
        await self._session.flush()

    # ---- for the matcher ------------------------------------------------------------------

    async def plans_for_matching(self, user_id: uuid.UUID) -> list[PlanRow]:
        """Every plan of the user's live purchases that is not cancelled, with its payments and
        which of them already have a bank row."""
        _check_user_id(user_id)
        statement = (
            select(InstallmentPlan, Transaction)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                Transaction.kind == TransactionKind.PURCHASE,
                InstallmentPlan.status != InstallmentPlanStatus.CANCELLED,
            )
        )
        rows = (await self._session.execute(statement)).all()
        if not rows:
            return []
        plan_ids = [plan.id for plan, _ in rows]
        payments = (
            (
                await self._session.execute(
                    select(InstallmentPayment)
                    .where(InstallmentPayment.plan_id.in_(plan_ids))
                    .order_by(InstallmentPayment.plan_id, InstallmentPayment.seq)
                )
            )
            .scalars()
            .all()
        )
        by_plan: dict[uuid.UUID, list[InstallmentPayment]] = {}
        for payment in payments:
            by_plan.setdefault(payment.plan_id, []).append(payment)
        linked = (
            await self._session.execute(
                select(Observation.installment_payment_id).where(
                    Observation.user_id == user_id,
                    Observation.status == ObservationStatus.CONFIRMED,
                    Observation.installment_payment_id.in_([p.id for p in payments]),
                )
            )
        ).scalars()
        linked_ids = frozenset(linked)
        return [
            PlanRow(plan, by_plan.get(plan.id, []), transaction, linked_ids)
            for plan, transaction in rows
        ]

    async def purchases_for_suggestions(
        self, user_id: uuid.UUID, *, since: date, until: date
    ) -> list[Transaction]:
        """The user's live purchases dated between `since` and `until` (for spec 8.3)."""
        _check_user_id(user_id)
        statement = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.kind == TransactionKind.PURCHASE,
            Transaction.purchase_date >= since,
            Transaction.purchase_date <= until,
        )
        return list((await self._session.execute(statement)).scalars().all())

    # ---- the schedule ---------------------------------------------------------------------

    async def schedule(
        self, user_id: uuid.UUID, *, from_month: date, to_month: date
    ) -> list[ScheduleRow]:
        _check_user_id(user_id)
        statement = (
            select(InstallmentPayment, InstallmentPlan, Transaction)
            .join(InstallmentPlan, InstallmentPlan.id == InstallmentPayment.plan_id)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                InstallmentPlan.status != InstallmentPlanStatus.CANCELLED,
                InstallmentPayment.due_month >= from_month,
                InstallmentPayment.due_month <= to_month,
            )
            .order_by(
                InstallmentPayment.due_month, Transaction.merchant_display, InstallmentPayment.seq
            )
        )
        return [
            ScheduleRow(payment, plan, transaction)
            for payment, plan, transaction in (await self._session.execute(statement)).all()
        ]

    async def remaining_from(self, user_id: uuid.UUID, month: date) -> int:
        """What is still expected: the EXPECTED payments of active plans from `month` on."""
        _check_user_id(user_id)
        statement = (
            select(func.coalesce(func.sum(InstallmentPayment.amount_minor), 0))
            .join(InstallmentPlan, InstallmentPlan.id == InstallmentPayment.plan_id)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                InstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
                InstallmentPayment.status == InstallmentPaymentStatus.EXPECTED,
                InstallmentPayment.due_month >= month,
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    # ---- the daily job ----------------------------------------------------------------------

    async def complete_finished(self, month: date) -> int:
        """ACTIVE plans whose last due month is before `month` become COMPLETED (all users: it is
        a maintenance job, it reads no user data)."""
        last_due = (
            select(
                InstallmentPayment.plan_id.label("plan_id"),
                func.max(InstallmentPayment.due_month).label("last_due"),
            )
            .group_by(InstallmentPayment.plan_id)
            .subquery()
        )
        finished = select(last_due.c.plan_id).where(last_due.c.last_due < month)
        result = await self._session.execute(
            update(InstallmentPlan)
            .where(
                and_(
                    InstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
                    InstallmentPlan.id.in_(finished),
                )
            )
            .values(status=InstallmentPlanStatus.COMPLETED)
        )
        return result.rowcount  # type: ignore[attr-defined]
