"""Installment endpoints (spec 8, 16, P10): plans and the payment schedule."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, TransactionServiceDep
from app.schemas.errors import ErrorResponse
from app.schemas.installments import PlanIn, PlanPatch, ScheduleOut
from app.schemas.transactions import TransactionDetail
from app.services.installment_schedule import add_months, first_of_month
from app.services.transaction_service import business_today

router = APIRouter(tags=["installments"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}


@router.put(
    "/transactions/{transaction_id}/installment-plan",
    response_model=TransactionDetail,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "PLAN_HAS_BANK_ROWS"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
    },
)
async def put_installment_plan(
    transaction_id: uuid.UUID,
    body: PlanIn,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> TransactionDetail:
    """ "Taksitli": the purchase is paid in `count` installments (2-36). Equal parts, the last one
    takes the rounding; the first is due the month after the purchase unless `first_due_month` is
    given; `total_payable_minor` is what the bank charges in all (default: the total). Replaces an
    existing plan as long as no bank row is attached to it."""
    return await service.put_plan(user.id, transaction_id, body)


@router.patch(
    "/installment-plans/{plan_id}",
    response_model=TransactionDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def patch_installment_plan(
    plan_id: uuid.UUID,
    body: PlanPatch,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> TransactionDetail:
    """Cancel or reopen a plan (`status`), move it (`first_due_month`) or change what the bank
    charges in all (`total_payable_minor`, at least the purchase total). Answers the purchase."""
    return await service.patch_plan(user.id, plan_id, body)


@router.get("/installments/schedule", response_model=ScheduleOut, responses=_UNAUTHORIZED)
async def installment_schedule(
    user: CurrentUser,
    service: TransactionServiceDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ScheduleOut:
    """The payments of the user's active plans by month (every month of the range is listed).
    Default range: this month and the next five. The payments are NOT spending: the purchase is
    counted once, in its purchase month, by the purchase list."""
    start = first_of_month(date_from or business_today())
    end = first_of_month(date_to) if date_to else add_months(start, 5)
    return await service.schedule(user.id, from_month=start, to_month=end)
