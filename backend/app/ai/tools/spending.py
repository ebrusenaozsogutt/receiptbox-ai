"""Spending tools: purchases, totals and period comparisons (spec 13.2). They reuse the P11
analytics SQL (`AnalyticsService`, `DashboardService.compare`) and the P07/P12 purchase list
(`TransactionService.list`): the numbers are the ones the app's screens show."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.ai.tools.base import (
    CATEGORY_LABELS,
    Action,
    Output,
    Tool,
    ToolArgs,
    ToolArgumentError,
    ToolContext,
    clamp_day,
    clamp_int,
    clamp_period,
    day_tr,
    month_tr,
    percent_tr,
    period_out,
    period_tr,
    tl,
)
from app.core.text import normalize_alias_key
from app.models.enums import CategoryKey, TransactionKind
from app.services.analytics import AnalyticsService, Group, compare_categories, month_end
from app.services.dashboard import DashboardService
from app.services.transaction_service import TransactionService

MAX_ROWS = 20
NOTHING_FOUND = "Kayıtlarında bununla ilgili bilgi bulamadım."


def _merchant_matches(wanted: str, merchant: str) -> bool:
    """Case- and punctuation-insensitive, Turkish-aware containment ('migros' ~ 'MİGROS')."""
    needle = normalize_alias_key(wanted)
    return bool(needle) and needle in normalize_alias_key(merchant)


def _list_action(
    date_from: date | None,
    date_to: date | None,
    category: CategoryKey | None,
    merchant: str | None,
    label: str = "Harcamaları gör",
) -> Action:
    params: dict[str, str] = {}
    if date_from is not None:
        params["from"] = date_from.isoformat()
    if date_to is not None:
        params["to"] = date_to.isoformat()
    if category is not None:
        params["category"] = category.value
    if merchant:
        params["q"] = merchant.strip()
    return Action("OPEN_TRANSACTIONS", label, params)


# ---- query_transactions ------------------------------------------------------------------------


class QueryTransactionsArgs(ToolArgs):
    merchant: str | None = Field(
        default=None, max_length=60, description="Part of the shop name, e.g. 'Migros'."
    )
    category: CategoryKey | None = Field(default=None, description="One of the category keys.")
    date_from: date | None = Field(default=None, description="First day, YYYY-MM-DD.")
    date_to: date | None = Field(default=None, description="Last day, YYYY-MM-DD.")
    min_amount: int | None = Field(
        default=None, ge=0, description="Smallest amount in whole Turkish lira."
    )
    max_amount: int | None = Field(
        default=None, ge=0, description="Largest amount in whole Turkish lira."
    )
    sort: Literal["date_desc", "amount_desc"] = Field(
        default="date_desc", description="Newest first, or most expensive first."
    )
    limit: int = Field(default=10, description="How many purchases to return, at most 20.")


async def _query_transactions(ctx: ToolContext, args: QueryTransactionsArgs) -> Output:
    date_from = clamp_day(ctx.today, args.date_from)
    date_to = clamp_day(ctx.today, args.date_to)
    if date_from and date_to and date_from > date_to:
        raise ToolArgumentError("date_from is after date_to; send the period in the right order.")
    limit = clamp_int(args.limit, 1, MAX_ROWS)
    page = await TransactionService(ctx.session, ctx.storage, ctx.settings).list(
        ctx.user_id,
        date_from=date_from,
        date_to=date_to,
        category=args.category,
        merchant_id=None,
        search=args.merchant.strip() if args.merchant else None,
        limit=limit,
        offset=0,
        min_minor=args.min_amount * 100 if args.min_amount is not None else None,
        max_minor=args.max_amount * 100 if args.max_amount is not None else None,
        order=args.sort,
    )
    rows = []
    for item in page.items:
        net = (
            -item.total_minor
            if item.kind == TransactionKind.REFUND
            else item.total_minor - item.refunded_minor
        )
        row = {
            "transaction_id": str(item.id),
            "date": item.purchase_date.isoformat(),
            "merchant": item.merchant_display,
            "category": CATEGORY_LABELS[item.category_key] if item.category_key else None,
            "amount": tl(net),
            "installments": item.payment_type == "INSTALLMENT",
        }
        if item.refunded_minor:
            row["refunded"] = tl(item.refunded_minor)
        rows.append(row)
    return {
        "period": period_out(date_from, date_to) if date_from and date_to else None,
        "matching_count": page.count,
        "matching_total": tl(page.sum_minor),
        "returned_count": len(rows),
        "sort": args.sort,
        "purchases": rows,
    }


def _query_actions(args: QueryTransactionsArgs, output: Output) -> list[Action]:
    if not output.get("matching_count"):
        return []
    period = output.get("period") or {}
    return [
        _list_action(
            date.fromisoformat(period["from"]) if period else args.date_from,
            date.fromisoformat(period["to"]) if period else args.date_to,
            args.category,
            args.merchant,
        )
    ]


def _query_summary(args: QueryTransactionsArgs, output: Output) -> str:
    purchases = output.get("purchases") or []
    if not purchases:
        return NOTHING_FOUND
    lines = [f"Bulduğum {len(purchases)} alışveriş:"]
    for row in purchases[:5]:
        lines.append(
            f"- {day_tr(date.fromisoformat(row['date']))}, {row['merchant']}: {row['amount']}"
        )
    return "\n".join(lines)


QUERY_TRANSACTIONS = Tool(
    name="query_transactions",
    description=(
        "Lists the user's purchases (net of refunds), filtered by shop, category, dates and "
        "amount; newest first or most expensive first. Also returns how many purchases match and "
        "their total."
    ),
    args_model=QueryTransactionsArgs,
    run=_query_transactions,
    actions=_query_actions,
    summary=_query_summary,
)


# ---- aggregate_spending ------------------------------------------------------------------------


class AggregateSpendingArgs(ToolArgs):
    date_from: date = Field(description="First day, YYYY-MM-DD.")
    date_to: date = Field(description="Last day, YYYY-MM-DD.")
    group_by: Literal["none", "category", "merchant", "month"] = Field(
        default="none", description="One total, or totals per category, shop or month."
    )
    category: CategoryKey | None = Field(default=None, description="Only this category.")
    merchant: str | None = Field(
        default=None, max_length=60, description="Only shops whose name contains this."
    )


def _groups(groups: list[Group], group_by: str) -> list[dict[str, str]]:
    out = []
    for g in groups:
        if group_by == "month":
            month = date.fromisoformat(f"{g.key}-01")
            out.append({"month": g.key, "label": month_tr(month), "total": tl(g.total_minor)})
        elif group_by == "category":
            out.append({"category": g.key, "label": g.label, "total": tl(g.total_minor)})
        else:
            out.append({"merchant": g.label, "total": tl(g.total_minor)})
    return out


async def _aggregate_spending(ctx: ToolContext, args: AggregateSpendingArgs) -> Output:
    date_from, date_to = clamp_period(ctx.today, args.date_from, args.date_to)
    merchant = args.merchant.strip() if args.merchant else None
    if merchant and args.group_by in ("category", "month"):
        raise ToolArgumentError(
            "merchant can only be combined with group_by 'none' or 'merchant'; "
            "use query_transactions for one shop's purchases."
        )
    analytics = AnalyticsService(ctx.session)
    groups: list[Group] = []
    if merchant:
        by_merchant = await analytics.spending_by(
            ctx.user_id, date_from, date_to, "merchant", category=args.category
        )
        groups = [g for g in by_merchant if _merchant_matches(merchant, g.label)]
        total = sum(g.total_minor for g in groups)
    else:
        total = await analytics.spending_total(
            ctx.user_id, date_from, date_to, category=args.category
        )
        if args.group_by != "none":
            groups = await analytics.spending_by(
                ctx.user_id, date_from, date_to, args.group_by, category=args.category
            )
    output: Output = {
        "period": period_out(date_from, date_to),
        "category": CATEGORY_LABELS[args.category] if args.category else None,
        "merchant_filter": merchant,
        "total": tl(total),
        "has_spending": total != 0 or bool(groups),
    }
    if args.group_by != "none" or merchant:
        output["groups"] = _groups(groups, "merchant" if merchant else args.group_by)
    return output


def _aggregate_actions(args: AggregateSpendingArgs, output: Output) -> list[Action]:
    if not output.get("has_spending"):
        return []
    period = output["period"]
    return [
        _list_action(
            date.fromisoformat(period["from"]),
            date.fromisoformat(period["to"]),
            args.category,
            args.merchant,
        )
    ]


def _aggregate_summary(args: AggregateSpendingArgs, output: Output) -> str:
    period = output["period"]
    when = period_tr(date.fromisoformat(period["from"]), date.fromisoformat(period["to"]))
    if not output.get("has_spending"):
        return f"{when} döneminde kayıtlı bir harcaman yok."
    what = "harcaman"
    if output.get("category"):
        what = f"{output['category']} kategorisindeki harcaman"
    if output.get("merchant_filter"):
        what = f'"{output["merchant_filter"]}" harcaman'
    lines = [f"{when} döneminde {what}: {output['total']}."]
    for group in (output.get("groups") or [])[:6]:
        name = group.get("label") or group.get("merchant")
        lines.append(f"- {name}: {group['total']}")
    return "\n".join(lines)


AGGREGATE_SPENDING = Tool(
    name="aggregate_spending",
    description=(
        "Total net spending (purchases minus refunds, by purchase date) of a period, optionally "
        "of one category or shop, optionally split by category, shop or month. Installment "
        "payments are not spending: a purchase counts once, in its purchase month."
    ),
    args_model=AggregateSpendingArgs,
    run=_aggregate_spending,
    actions=_aggregate_actions,
    summary=_aggregate_summary,
)


# ---- compare_periods ---------------------------------------------------------------------------


class ComparePeriodsArgs(ToolArgs):
    a_from: date = Field(description="Period A, first day (usually the more recent period).")
    a_to: date = Field(description="Period A, last day.")
    b_from: date = Field(description="Period B, first day.")
    b_to: date = Field(description="Period B, last day.")
    group_by: Literal["none", "category"] = Field(
        default="none", description="Also compare every category."
    )


async def _compare_periods(ctx: ToolContext, args: ComparePeriodsArgs) -> Output:
    a = clamp_period(ctx.today, args.a_from, args.a_to)
    b = clamp_period(ctx.today, args.b_from, args.b_to)
    dashboard = DashboardService(ctx.session)
    result = await dashboard.compare(ctx.user_id, a, b)
    changes: list = list(result.top_categories)
    if args.group_by == "category":
        changes = await compare_categories(
            AnalyticsService(ctx.session), ctx.user_id, a, b, top=len(CategoryKey)
        )
    categories = [
        {"label": c.label, "a": tl(c.a_minor), "b": tl(c.b_minor), "difference": tl(c.delta_minor)}
        for c in changes
    ]
    if result.delta_minor > 0:
        direction = "A dönemi daha yüksek"
    elif result.delta_minor < 0:
        direction = "A dönemi daha düşük"
    else:
        direction = "iki dönem eşit"
    return {
        "a": {**period_out(*a), "total": tl(result.a.total_minor)},
        "b": {**period_out(*b), "total": tl(result.b.total_minor)},
        "difference_a_minus_b": tl(result.delta_minor),
        "difference_abs": tl(abs(result.delta_minor)),
        "change_percent": percent_tr(result.delta_pct) if result.delta_pct is not None else None,
        "direction": direction,
        "categories_that_changed_most": categories,
    }


def _period_label(date_from: date, date_to: date) -> str:
    """'Kasım 2026 harcamaları' for a whole month, '2025 harcamaları' for a whole year, else the
    two days (found on the emulator: "A dönemini gör" did not say which period)."""
    if date_from.day == 1 and date_to == month_end(date_from):
        return f"{month_tr(date_from)} harcamaları"
    if (date_from.month, date_from.day, date_to.month, date_to.day) == (1, 1, 12, 31) and (
        date_from.year == date_to.year
    ):
        return f"{date_from.year} harcamaları"
    return f"{period_tr(date_from, date_to)} harcamaları"


def _compare_actions(args: ComparePeriodsArgs, output: Output) -> list[Action]:
    actions = []
    for side in ("a", "b"):
        date_from = date.fromisoformat(output[side]["from"])
        date_to = date.fromisoformat(output[side]["to"])
        actions.append(
            _list_action(date_from, date_to, None, None, _period_label(date_from, date_to))
        )
    return actions


def _compare_summary(args: ComparePeriodsArgs, output: Output) -> str:
    a, b = output["a"], output["b"]
    a_when = period_tr(date.fromisoformat(a["from"]), date.fromisoformat(a["to"]))
    b_when = period_tr(date.fromisoformat(b["from"]), date.fromisoformat(b["to"]))
    text = f"{a_when}: {a['total']}. {b_when}: {b['total']}. Fark: {output['difference_abs']}"
    if output.get("change_percent"):
        text += f" ({output['change_percent']})"
    return text + "."


COMPARE_PERIODS = Tool(
    name="compare_periods",
    description=(
        "Compares the net spending of two periods: both totals, the difference (A minus B), the "
        "change in percent and the categories that changed most."
    ),
    args_model=ComparePeriodsArgs,
    run=_compare_periods,
    actions=_compare_actions,
    summary=_compare_summary,
)
