"""Deadline and installment tools (spec 13.2). Deadlines come from the same queries the P13
reminders are computed from (`ReminderRepository`: ACTIVE products, OPEN return windows, ACTIVE
plans of purchases that are not deleted); the schedule is the P10 one
(`TransactionService.schedule`, also behind the Taksitler screen)."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import Field, WithJsonSchema, field_validator

from app.ai.tools.base import (
    Action,
    Output,
    Tool,
    ToolArgs,
    ToolContext,
    clamp_int,
    clamp_months,
    day_tr,
    month_key,
    month_tr,
    tl,
)
from app.models.enums import InstallmentPaymentStatus
from app.repositories.reminders import ReminderRepository
from app.services.installment_schedule import first_of_month
from app.services.transaction_service import TransactionService

_MONTH_PATTERN = r"^\d{4}-\d{2}$"
DeadlineType = Literal["WARRANTY", "RETURN", "INSTALLMENT_END"]
MAX_DEADLINES = 20
MAX_PRODUCT_ACTIONS = 3

PAYMENT_STATUS_TR = {
    InstallmentPaymentStatus.OBSERVED: "ödendi (ekstrede görüldü)",
    InstallmentPaymentStatus.INFERRED: "ödendi sayıldı",
    InstallmentPaymentStatus.EXPECTED: "bekleniyor",
}


# ---- get_upcoming_deadlines --------------------------------------------------------------------


class UpcomingDeadlinesArgs(ToolArgs):
    days: int = Field(default=30, description="How many days ahead to look, at most 365.")
    types: list[DeadlineType] | None = Field(
        default=None, description="Which deadlines; empty means all three."
    )


async def _upcoming_deadlines(ctx: ToolContext, args: UpcomingDeadlinesArgs) -> Output:
    days = clamp_int(args.days, 1, 365)
    wanted = set(args.types or ("WARRANTY", "RETURN", "INSTALLMENT_END"))
    until = ctx.today + timedelta(days=days)
    repo = ReminderRepository(ctx.session)
    items: list[dict[str, Any]] = []

    if wanted & {"WARRANTY", "RETURN"}:
        deadlines = await repo.product_deadlines(ctx.user_id)
        names = await repo.products(ctx.user_id, [d.product_id for d in deadlines])
        for d in deadlines:
            target = names.get(d.product_id)
            if target is None:
                continue
            for kind, end in (("WARRANTY", d.warranty_end), ("RETURN", d.return_end)):
                if kind in wanted and end is not None and ctx.today <= end <= until:
                    items.append(
                        {
                            "type": kind,
                            "date": end.isoformat(),
                            "days_left": (end - ctx.today).days,
                            "product_id": str(d.product_id),
                            "product": target.name,
                            "merchant": target.merchant_display,
                        }
                    )

    if "INSTALLMENT_END" in wanted:
        plans = await repo.plan_deadlines(ctx.user_id)
        targets = await repo.plans(ctx.user_id, [p.plan_id for p in plans])
        this_month = first_of_month(ctx.today)
        for plan in plans:
            last = plan.last_due_month
            target = targets.get(plan.plan_id)
            if target is not None and this_month <= last <= until:
                items.append(
                    {
                        "type": "INSTALLMENT_END",
                        "date": last.isoformat(),
                        "month": month_key(last),
                        "transaction_id": str(target.transaction_id),
                        "merchant": target.merchant_display,
                        "installment_count": plan.count,
                    }
                )

    items.sort(key=lambda item: (item["date"], item["type"]))
    return {
        "today": ctx.today.isoformat(),
        "until": until.isoformat(),
        "days": days,
        "count": len(items),
        "deadlines": items[:MAX_DEADLINES],
    }


def _deadline_actions(args: UpcomingDeadlinesArgs, output: Output) -> list[Action]:
    actions: list[Action] = []
    seen: set[str] = set()
    for item in output.get("deadlines") or []:
        if item["type"] == "INSTALLMENT_END":
            key = f"month:{item['month']}"
            if key not in seen:
                seen.add(key)
                actions.append(
                    Action("OPEN_INSTALLMENTS", "Taksitleri gör", {"month": item["month"]})
                )
        elif item["product_id"] not in seen:
            seen.add(item["product_id"])
            actions.append(
                Action("OPEN_PRODUCT", f"{item['product']} kartı", {"id": item["product_id"]})
            )
        if len(actions) >= MAX_PRODUCT_ACTIONS:
            break
    return actions


def _deadline_summary(args: UpcomingDeadlinesArgs, output: Output) -> str:
    items = output.get("deadlines") or []
    if not items:
        return f"Önümüzdeki {output['days']} günde biten bir garanti, iade ya da taksit yok."
    lines = [f"Önümüzdeki {output['days']} günde:"]
    for item in items[:6]:
        when = date.fromisoformat(item["date"])
        if item["type"] == "WARRANTY":
            lines.append(f"- {item['product']}: garanti {day_tr(when)} ({item['days_left']} gün)")
        elif item["type"] == "RETURN":
            lines.append(f"- {item['product']}: iade {day_tr(when)} ({item['days_left']} gün)")
        else:
            lines.append(f"- {item['merchant']}: son taksit {month_tr(when)}")
    return "\n".join(lines)


GET_UPCOMING_DEADLINES = Tool(
    name="get_upcoming_deadlines",
    description=(
        "Deadlines from today on: warranty ends and last days to return a product (with the days "
        "left), and the month of the last installment of each installment purchase."
    ),
    args_model=UpcomingDeadlinesArgs,
    run=_upcoming_deadlines,
    actions=_deadline_actions,
    summary=_deadline_summary,
)


# ---- get_installment_schedule ------------------------------------------------------------------


def _month(value: object) -> object:
    """'2026-11' or '2026-11-15' -> the first day of that month."""
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.strptime(text[:7], "%Y-%m").date()
        except ValueError:
            raise ValueError("Use YYYY-MM.") from None
        return parsed
    return value


class InstallmentScheduleArgs(ToolArgs):
    month_from: Annotated[date, WithJsonSchema({"type": "string", "pattern": _MONTH_PATTERN})] = (
        Field(description="First month, YYYY-MM.")
    )
    month_to: Annotated[date, WithJsonSchema({"type": "string", "pattern": _MONTH_PATTERN})] = (
        Field(description="Last month, YYYY-MM (at most 24 months after month_from).")
    )

    _months = field_validator("month_from", "month_to", mode="before")(_month)


async def _installment_schedule(ctx: ToolContext, args: InstallmentScheduleArgs) -> Output:
    month_from, month_to = clamp_months(ctx.today, args.month_from, args.month_to)
    schedule = await TransactionService(ctx.session, ctx.storage, ctx.settings).schedule(
        ctx.user_id, from_month=month_from, to_month=month_to
    )
    months = [
        {
            "month": month_key(m.month),
            "label": month_tr(m.month),
            "total": tl(m.total_minor),
            "not_seen_on_statement_yet": tl(m.expected_minor),
            "payments": [
                {
                    "merchant": item.merchant_display,
                    "installment": f"{item.seq}/{item.count}",
                    "amount": tl(item.amount_minor),
                    "status": PAYMENT_STATUS_TR[item.status],
                    "transaction_id": str(item.transaction_id),
                }
                for item in m.items
            ],
        }
        for m in schedule.months
        if m.items
    ]
    return {
        "month_from": month_key(month_from),
        "month_to": month_key(month_to),
        "months": months,
        "remaining_total_from_this_month": tl(schedule.remaining_minor),
        "remaining_note": (
            "remaining_total_from_this_month = every payment still expected from the current "
            "month on, over all plans, whatever months were asked for."
        ),
    }


def _schedule_actions(args: InstallmentScheduleArgs, output: Output) -> list[Action]:
    months = output.get("months") or []
    month = months[0]["month"] if months else output["month_from"]
    return [Action("OPEN_INSTALLMENTS", "Taksitleri gör", {"month": month})]


def _schedule_summary(args: InstallmentScheduleArgs, output: Output) -> str:
    remaining = output["remaining_total_from_this_month"]
    lines = [f"Bu aydan itibaren kalan taksitlerin toplamı {remaining}."]
    for m in (output.get("months") or [])[:6]:
        lines.append(f"- {m['label']}: {m['total']}")
    return "\n".join(lines)


GET_INSTALLMENT_SCHEDULE = Tool(
    name="get_installment_schedule",
    description=(
        "Installment payments by due month (amount, k/n, paid or expected) and the total still "
        "to pay from the current month on over all installment purchases."
    ),
    args_model=InstallmentScheduleArgs,
    run=_installment_schedule,
    actions=_schedule_actions,
    summary=_schedule_summary,
)
