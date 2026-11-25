"""Analytics and budget endpoints (spec 11, 16, P11). No logic here: see services/dashboard.py
(shapes), services/analytics.py (the SQL) and services/budget_service.py."""

import asyncio
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import (
    CommentaryCacheDep,
    CurrentUser,
    DashboardServiceDep,
    OptionalAIProvider,
)
from app.core.errors import ValidationFailedError
from app.models.enums import CategoryKey
from app.schemas.analytics import CommentaryOut, CompareOut, HomeOut, SpendingOut, YearOut
from app.schemas.budgets import BudgetIn, BudgetsOut
from app.schemas.errors import ErrorResponse
from app.services.analytics import month_end
from app.services.commentary import write_commentary
from app.services.installment_schedule import first_of_month

router = APIRouter(tags=["analytics"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_INVALID = {422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"}}

MonthParam = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")]


def _month(value: str | None, today: date) -> date:
    if value is None:
        return first_of_month(today)
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _period(date_from: date, date_to: date) -> tuple[date, date]:
    if date_from > date_to:
        raise ValidationFailedError("`from` must not be after `to`.")
    return date_from, date_to


@router.get("/analytics/home", response_model=HomeOut, responses={**_UNAUTHORIZED, **_INVALID})
async def home(
    user: CurrentUser, service: DashboardServiceDep, month: MonthParam = None
) -> HomeOut:
    """The home screen of one month (default: this month), in its fixed order: spending (net of
    refunds, by purchase month; installment payments are NOT in it), what needs attention
    (budgets at 80 % or more; returns and warranties from P12) and the installment payments due,
    with the next six months."""
    return await service.home(user.id, _month(month, service.today()))


@router.get(
    "/analytics/spending", response_model=SpendingOut, responses={**_UNAUTHORIZED, **_INVALID}
)
async def spending(
    user: CurrentUser,
    service: DashboardServiceDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    group_by: Literal["category", "merchant", "month", "week"] = "category",
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> SpendingOut:
    """Net spending of a period (default: this month) by category, merchant, month or ISO week.
    `limit` applies to categories and merchants (largest first)."""
    start = date_from or first_of_month(service.today())
    end = date_to or month_end(start)
    return await service.spending(user.id, *_period(start, end), group_by, limit)


@router.get(
    "/analytics/compare", response_model=CompareOut, responses={**_UNAUTHORIZED, **_INVALID}
)
async def compare(
    user: CurrentUser,
    service: DashboardServiceDep,
    a_from: date,
    a_to: date,
    b_from: date,
    b_to: date,
) -> CompareOut:
    """Period `a` compared with period `b` (delta = a - b) and the three categories that changed
    most."""
    return await service.compare(user.id, _period(a_from, a_to), _period(b_from, b_to))


@router.get(
    "/analytics/compare/commentary",
    response_model=CommentaryOut,
    responses={**_UNAUTHORIZED, **_INVALID},
)
async def compare_commentary(
    user: CurrentUser,
    service: DashboardServiceDep,
    provider: OptionalAIProvider,
    cache: CommentaryCacheDep,
    a_from: date,
    a_to: date,
    b_from: date,
    b_to: date,
) -> CommentaryOut:
    """Optional: at most two sentences about the comparison, written by the AI from the computed
    numbers only (never transactions or shops). Null without AI consent or when the AI fails."""
    result = await service.compare(user.id, _period(a_from, a_to), _period(b_from, b_to))
    if not user.ai_consent:
        return CommentaryOut(commentary=None)
    text = await asyncio.to_thread(write_commentary, provider, cache, user.id, result)
    return CommentaryOut(commentary=text)


@router.get("/analytics/year", response_model=YearOut, responses={**_UNAUTHORIZED, **_INVALID})
async def year(
    user: CurrentUser,
    service: DashboardServiceDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> YearOut:
    """One year: total, by category, all twelve months and the ten merchants with most spending."""
    return await service.year(user.id, year or service.today().year)


# ---- budgets ------------------------------------------------------------------------------------


@router.get("/budgets", response_model=BudgetsOut, responses={**_UNAUTHORIZED, **_INVALID})
async def list_budgets(
    user: CurrentUser, service: DashboardServiceDep, month: MonthParam = None
) -> BudgetsOut:
    """The monthly limits and their use in `month` (default: this month), measured on the
    spending view."""
    return await service.budgets(user.id, _month(month, service.today()))


@router.put("/budgets", response_model=BudgetsOut, responses={**_UNAUTHORIZED, **_INVALID})
async def put_budget(user: CurrentUser, service: DashboardServiceDep, body: BudgetIn) -> BudgetsOut:
    """Set (or change) the monthly limit of one category. Answers the budgets of this month."""
    return await service.put_budget(user.id, body.category_key, body.monthly_limit_minor)


@router.delete(
    "/budgets/{category_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, 404: {"model": ErrorResponse, "description": "NOT_FOUND"}},
)
async def delete_budget(
    category_key: CategoryKey, user: CurrentUser, service: DashboardServiceDep
) -> Response:
    await service.delete_budget(user.id, category_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
