"""Installment plans, their payments and the matching of bank installment rows (spec 8, P10).

One installment purchase is ONE spending (the transaction, counted in its purchase month) and N
payments. Payments are never added to spending: they only feed the schedule. This service keeps
that rule by never touching `transactions.total_minor` for a payment, and by attaching a bank row
to a payment (`observations.installment_payment_id`) instead of making a purchase of it.

The scoring is in `app/matching/installment_matcher.py` (pure). Here: the database parts. Every
read goes through the user's purchases (a plan has no user_id); another user's plan is a 404.
Nothing here logs merchant names or amounts.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    MatchNotAvailableError,
    NotFoundError,
    PlanHasBankRowsError,
    ValidationFailedError,
)
from app.matching.installment_matcher import (
    InstallmentMatch,
    InstallmentOutcome,
    InstallmentRow,
    InstallmentSuggestion,
    PaymentView,
    PlanView,
    PurchaseView,
    amount_tolerance,
    estimate_purchase,
    match_installment_row,
    suggest_for_markerless_row,
)
from app.models import InstallmentPayment, InstallmentPlan, Observation, Transaction
from app.models.enums import (
    InstallmentPaymentStatus,
    InstallmentPlanStatus,
    MatchDecisionStatus,
    MatchType,
    ObservationStatus,
    PaymentType,
)
from app.repositories.installments import InstallmentRepository, PlanRow
from app.repositories.matches import MatchDecisionRepository
from app.schemas.installments import (
    PaymentOut,
    PlanOut,
    ScheduleItemOut,
    ScheduleMonthOut,
    ScheduleOut,
)
from app.services.installment_schedule import (
    MAX_INSTALLMENTS,
    MIN_INSTALLMENTS,
    add_months,
    default_first_due_month,
    first_of_month,
    month_index,
    split_total,
)

CAPTURE_DATE_KEY = "capture_date"  # extraction_json key written by the bank import (P10)


def _now() -> datetime:
    return datetime.now().astimezone()


def validate_count(count: int) -> int:
    if not MIN_INSTALLMENTS <= count <= MAX_INSTALLMENTS:
        raise ValidationFailedError(
            f"The installment count must be between {MIN_INSTALLMENTS} and {MAX_INSTALLMENTS}."
        )
    return count


@dataclass(frozen=True)
class RowContext:
    """The bank row as the matcher needs it, plus what is needed to create things for it."""

    row: InstallmentRow
    merchant_id: uuid.UUID | None


def capture_date_of(observation: Observation, today: date) -> date:
    """The day the screenshot was taken (the statement month), as the bank import saved it."""
    captured = (observation.extraction_json or {}).get(CAPTURE_DATE_KEY)
    return date.fromisoformat(captured) if captured else today


def row_context(observation: Observation, today: date) -> RowContext | None:
    """The matcher's view of a pending bank row, or None when it has no date or amount."""
    if observation.obs_date is None or not observation.amount_minor:
        return None
    saved: dict[str, Any] = observation.extraction_json or {}
    raw_merchant_id = ((saved.get("suggestions") or {}).get("merchant") or {}).get("merchant_id")
    capture_date = capture_date_of(observation, today)
    return RowContext(
        InstallmentRow(
            merchant_id=None,
            merchant_name=observation.merchant_raw or "",
            amount_minor=observation.amount_minor,
            seq=observation.installment_seq,
            count=observation.installment_count,
            row_date=observation.obs_date,
            capture_date=capture_date,
        ),
        uuid.UUID(raw_merchant_id) if raw_merchant_id else None,
    )


class InstallmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = InstallmentRepository(session)
        self._decisions = MatchDecisionRepository(session)

    # ---- plans ----------------------------------------------------------------------------

    async def create_plan(
        self,
        transaction: Transaction,
        *,
        count: int,
        first_due_month: date | None = None,
        total_payable_minor: int | None = None,
        inferred_before: int | None = None,
    ) -> InstallmentPlan:
        """Spec 8.1: `count` payments of the total (the last one takes the rounding), the first
        due the month after the purchase unless told otherwise. `inferred_before`: payments with
        a smaller number are INFERRED (a later one was seen on a statement)."""
        validate_count(count)
        total = total_payable_minor if total_payable_minor is not None else transaction.total_minor
        first_due = first_of_month(
            first_due_month or default_first_due_month(transaction.purchase_date)
        )
        parts = split_total(total, count)
        plan = self._repo.add_plan(
            transaction.id,
            count=count,
            installment_minor=parts[0],
            total_payable_minor=total,
            first_due_month=first_due,
        )
        await self._session.flush()
        for index, amount in enumerate(parts):
            seq = index + 1
            self._repo.add_payment(
                plan.id,
                seq=seq,
                due_month=add_months(first_due, index),
                amount_minor=amount,
                status=(
                    InstallmentPaymentStatus.INFERRED
                    if inferred_before is not None and seq < inferred_before
                    else InstallmentPaymentStatus.EXPECTED
                ),
            )
        transaction.payment_type = PaymentType.INSTALLMENT
        await self._session.flush()
        return plan

    async def replace_plan(
        self,
        user_id: uuid.UUID,
        transaction: Transaction,
        *,
        count: int,
        first_due_month: date | None,
        total_payable_minor: int | None,
    ) -> InstallmentPlan:
        """`PUT /transactions/{id}/installment-plan`: create the plan, or replace it while no bank
        row is attached to it."""
        if total_payable_minor is not None and total_payable_minor < transaction.total_minor:
            raise ValidationFailedError("The amount to be paid cannot be below the total.")
        existing = await self._repo.plan_of_transaction(user_id, transaction.id)
        if existing is not None:
            if await self._has_bank_rows(user_id, existing):
                raise PlanHasBankRowsError()
            await self._repo.delete_plan(existing)
        return await self.create_plan(
            transaction,
            count=count,
            first_due_month=first_due_month,
            total_payable_minor=total_payable_minor,
        )

    async def patch_plan(
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        *,
        status: str | None,
        first_due_month: date | None,
        total_payable_minor: int | None,
        sent: set[str],
    ) -> Transaction:
        plan = await self._repo.plan(user_id, plan_id)
        if plan is None:
            raise NotFoundError()
        transaction = await self._session.get(Transaction, plan.transaction_id)
        assert transaction is not None  # noqa: S101 (the plan was found through it)
        payments = await self._repo.payments(plan.id)
        if "first_due_month" in sent and first_due_month is not None:
            first = first_of_month(first_due_month)
            plan.first_due_month = first
            for payment in payments:
                payment.due_month = add_months(first, payment.seq - 1)
        if "total_payable_minor" in sent and total_payable_minor is not None:
            if total_payable_minor < transaction.total_minor:
                raise ValidationFailedError("The amount to be paid cannot be below the total.")
            plan.total_payable_minor = total_payable_minor
            parts = split_total(total_payable_minor, plan.count)
            plan.installment_minor = parts[0]
            for payment in payments:
                payment.amount_minor = parts[payment.seq - 1]
        if "status" in sent and status is not None:
            plan.status = InstallmentPlanStatus(status)
            if plan.status == InstallmentPlanStatus.CANCELLED:
                transaction.payment_type = PaymentType.SINGLE
            else:
                transaction.payment_type = PaymentType.INSTALLMENT
        await self._session.flush()
        return transaction

    async def plan_by_id(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> InstallmentPlan:
        plan = await self._repo.plan(user_id, plan_id)
        if plan is None:
            raise NotFoundError()
        return plan

    async def follow_total(
        self, user_id: uuid.UUID, transaction: Transaction, old_total_minor: int
    ) -> None:
        """The purchase total was edited: a plan that charged exactly the old total is spread
        again from the new one (a plan with a financing cost keeps its own total)."""
        plan = await self._repo.plan_of_transaction(user_id, transaction.id)
        if plan is None or plan.total_payable_minor != old_total_minor:
            return
        plan.total_payable_minor = transaction.total_minor
        parts = split_total(transaction.total_minor, plan.count)
        plan.installment_minor = parts[0]
        for payment in await self._repo.payments(plan.id):
            payment.amount_minor = parts[payment.seq - 1]
        await self._session.flush()

    async def plan_out(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> PlanOut | None:
        plan = await self._repo.plan_of_transaction(user_id, transaction_id)
        if plan is None:
            return None
        payments = await self._repo.payments(plan.id)
        return PlanOut(
            id=plan.id,
            count=plan.count,
            installment_minor=plan.installment_minor,
            total_payable_minor=plan.total_payable_minor,
            first_due_month=plan.first_due_month,
            status=plan.status,
            payments=[
                PaymentOut(
                    id=p.id,
                    seq=p.seq,
                    due_month=p.due_month,
                    amount_minor=p.amount_minor,
                    status=p.status,
                )
                for p in payments
            ],
        )

    async def _has_bank_rows(self, user_id: uuid.UUID, plan: InstallmentPlan) -> bool:
        for row in await self._repo.plans_for_matching(user_id):
            if row.plan.id == plan.id:
                return bool(row.linked_payment_ids)
        return False

    # ---- linking a bank row to a payment -----------------------------------------------------

    async def link_payment(
        self, observation: Observation, plan: InstallmentPlan, seq: int
    ) -> InstallmentPayment:
        """The row becomes payment `seq`: OBSERVED, the earlier EXPECTED ones INFERRED. The row is
        attached to the purchase as evidence but makes no purchase of its own."""
        payments = await self._repo.payments(plan.id)
        payment = next((p for p in payments if p.seq == seq), None)
        if payment is None:
            raise MatchNotAvailableError()
        payment.status = InstallmentPaymentStatus.OBSERVED
        for earlier in payments:
            if earlier.seq < seq and earlier.status == InstallmentPaymentStatus.EXPECTED:
                earlier.status = InstallmentPaymentStatus.INFERRED
        observation.installment_payment_id = payment.id
        observation.transaction_id = plan.transaction_id
        observation.status = ObservationStatus.CONFIRMED
        await self._session.flush()
        return payment

    # ---- matching rows --------------------------------------------------------------------------

    async def plan_views(self, user_id: uuid.UUID) -> list[PlanView]:
        return [_view(row) for row in await self._repo.plans_for_matching(user_id)]

    async def match_row(self, user_id: uuid.UUID, context: RowContext) -> InstallmentMatch:
        """Spec 8.2 steps 1-2 for a row with a marker. Writes nothing."""
        views = await self.plan_views(user_id)
        # the shop the app already knows (alias) counts as the same shop on the plan side too
        row = InstallmentRow(
            context.merchant_id,
            context.row.merchant_name,
            context.row.amount_minor,
            context.row.seq,
            context.row.count,
            context.row.row_date,
            context.row.capture_date,
        )
        return match_installment_row(row, views)

    async def record_row_candidates(
        self, user_id: uuid.UUID, observation_id: uuid.UUID, match: InstallmentMatch
    ) -> dict[uuid.UUID, Any]:
        """Store every candidate with its features (`match_type=INSTALLMENT`, P15 learns from
        them): the linked one AUTO_ACCEPTED, tied ones PENDING (the user chooses), the rest
        REJECTED. Returns transaction id -> decision."""
        await self._decisions.delete_pending_for_observation(user_id, observation_id)
        saved: dict[uuid.UUID, Any] = {}
        for candidate in match.candidates:
            if match.outcome == InstallmentOutcome.LINK and candidate is match.best:
                status = MatchDecisionStatus.AUTO_ACCEPTED
            elif match.outcome == InstallmentOutcome.AMBIGUOUS and candidate in match.eligible:
                status = MatchDecisionStatus.PENDING
            else:
                status = MatchDecisionStatus.REJECTED
            saved[candidate.plan.transaction_id] = await self._decisions.add(
                user_id,
                observation_id=observation_id,
                transaction_id=candidate.plan.transaction_id,
                installment_payment_id=None,
                match_type=MatchType.INSTALLMENT,
                score=Decimal(str(candidate.features.ranking_score)),
                features_json=candidate.features.as_json(),
                decision=status,
                decided_at=None if status == MatchDecisionStatus.PENDING else _now(),
            )
        return saved

    async def suggest_for_row(
        self, user_id: uuid.UUID, context: RowContext
    ) -> list[InstallmentSuggestion]:
        """Spec 8.3: a row without a marker that may be one payment of an earlier purchase."""
        row = context.row
        since = add_months(row.row_date, -13)
        purchases = await self._repo.purchases_for_suggestions(
            user_id, since=since, until=row.row_date
        )
        plans = {view.transaction_id: view for view in await self.plan_views(user_id)}
        views = [
            PurchaseView(
                transaction_id=t.id,
                merchant_id=t.merchant_id,
                merchant_name=t.merchant_display,
                purchase_date=t.purchase_date,
                total_minor=t.total_minor,
                plan=plans.get(t.id),
            )
            for t in purchases
        ]
        marker_less = InstallmentRow(
            context.merchant_id,
            row.merchant_name,
            row.amount_minor,
            None,
            None,
            row.row_date,
            row.capture_date,
        )
        return suggest_for_markerless_row(marker_less, views)

    async def record_suggestions(
        self,
        user_id: uuid.UUID,
        observation_id: uuid.UUID,
        suggestions: list[InstallmentSuggestion],
    ) -> list[Any]:
        """Marker-less suggestions are PENDING only (spec 8.3: never automatic)."""
        await self._decisions.delete_pending_for_observation(user_id, observation_id)
        saved = []
        for suggestion in suggestions:
            saved.append(
                await self._decisions.add(
                    user_id,
                    observation_id=observation_id,
                    transaction_id=suggestion.purchase.transaction_id,
                    match_type=MatchType.INSTALLMENT,
                    score=Decimal(str(suggestion.features.ranking_score)),
                    features_json=suggestion.features.as_json(),
                    decision=MatchDecisionStatus.PENDING,
                    decided_at=None,
                )
            )
        return saved

    async def accept_installment(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        transaction_id: uuid.UUID,
        *,
        seq: int,
        count: int,
    ) -> Transaction:
        """The user said "yes, it is payment `seq` of `count` of that purchase": the plan is
        created when the purchase has none, the row is linked, no purchase is made."""
        transaction = await self._session.get(Transaction, transaction_id)
        if transaction is None or transaction.user_id != user_id or transaction.deleted_at:
            raise MatchNotAvailableError()
        plan = await self._repo.plan_of_transaction(user_id, transaction.id)
        if plan is None:
            plan = await self.create_plan(transaction, count=count, inferred_before=seq)
        elif plan.count != count or plan.status == InstallmentPlanStatus.CANCELLED:
            raise MatchNotAvailableError()
        for row in await self._repo.plans_for_matching(user_id):
            if row.plan.id == plan.id:
                payment = next((p for p in row.payments if p.seq == seq), None)
                if payment is None or payment.id in row.linked_payment_ids:
                    raise MatchNotAvailableError()
        await self.link_payment(observation, plan, seq)
        return transaction

    # ---- estimated purchases -----------------------------------------------------------------

    def estimate(self, context: RowContext, *, row_date_is_purchase_date: bool):  # noqa: ANN201
        return estimate_purchase(context.row, row_date_is_purchase_date=row_date_is_purchase_date)

    # ---- a receipt arrives for an estimated purchase ------------------------------------------

    async def on_receipt_merged(
        self,
        user_id: uuid.UUID,
        transaction: Transaction,
        *,
        receipt_count: int | None,
        clears_estimate: bool,
    ) -> None:
        """P09 merged a receipt (or any record that knows the real total) into a purchase that was
        only estimated from a bank row: it is no longer an estimate. When what the bank charges
        (the plan's total) is within the usual tolerance of the real total the payments are spread
        from the real total again; when it is clearly more, that difference is the financing cost
        and the payments stay as the bank charged them (spec 8.1)."""
        plan = await self._repo.plan_of_transaction(user_id, transaction.id)
        if transaction.is_estimated and clears_estimate:
            transaction.is_estimated = False
        if plan is None:
            if receipt_count is not None and receipt_count >= MIN_INSTALLMENTS:
                await self.create_plan(transaction, count=receipt_count)
            return
        if (
            clears_estimate
            and plan.total_payable_minor != transaction.total_minor
            and abs(plan.total_payable_minor - transaction.total_minor)
            <= amount_tolerance(transaction.total_minor)
        ):
            plan.total_payable_minor = transaction.total_minor
            parts = split_total(transaction.total_minor, plan.count)
            plan.installment_minor = parts[0]
            for payment in await self._repo.payments(plan.id):
                payment.amount_minor = parts[payment.seq - 1]
        await self._session.flush()

    # ---- the schedule -------------------------------------------------------------

    async def schedule(
        self, user_id: uuid.UUID, *, from_month: date, to_month: date, today: date
    ) -> ScheduleOut:
        rows = await self._repo.schedule(
            user_id, from_month=first_of_month(from_month), to_month=first_of_month(to_month)
        )
        months: dict[date, list[ScheduleItemOut]] = {}
        for row in rows:
            months.setdefault(row.payment.due_month, []).append(
                ScheduleItemOut(
                    payment_id=row.payment.id,
                    transaction_id=row.transaction.id,
                    merchant_display=row.transaction.merchant_display,
                    seq=row.payment.seq,
                    count=row.plan.count,
                    due_month=row.payment.due_month,
                    amount_minor=row.payment.amount_minor,
                    status=row.payment.status,
                    is_estimated=row.transaction.is_estimated,
                )
            )
        # every month of the range is listed, also the empty ones (a chart needs them)
        first, last = first_of_month(from_month), first_of_month(to_month)
        out: list[ScheduleMonthOut] = []
        for index in range(month_index(last) - month_index(first) + 1):
            month = add_months(first, index)
            items = months.get(month, [])
            out.append(
                ScheduleMonthOut(
                    month=month,
                    total_minor=sum(i.amount_minor for i in items),
                    expected_minor=sum(
                        i.amount_minor
                        for i in items
                        if i.status == InstallmentPaymentStatus.EXPECTED
                    ),
                    items=items,
                )
            )
        remaining = await self._repo.remaining_from(user_id, first_of_month(today))
        return ScheduleOut(months=out, remaining_minor=remaining)

    async def complete_finished_plans(self, today: date) -> int:
        """ACTIVE -> COMPLETED once the last due month is over (startup and schedule requests)."""
        return await self._repo.complete_finished(first_of_month(today))


def _view(row: PlanRow) -> PlanView:
    return PlanView(
        plan_id=row.plan.id,
        transaction_id=row.transaction.id,
        merchant_id=row.transaction.merchant_id,
        merchant_name=row.transaction.merchant_display,
        purchase_date=row.transaction.purchase_date,
        is_estimated=row.transaction.is_estimated,
        count=row.plan.count,
        payments=tuple(
            PaymentView(
                seq=payment.seq,
                due_month=payment.due_month,
                amount_minor=payment.amount_minor,
                linked=payment.id in row.linked_payment_ids,
            )
            for payment in row.payments
        ),
    )
