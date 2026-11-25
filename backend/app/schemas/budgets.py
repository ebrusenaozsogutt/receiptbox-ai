"""Budget request and response shapes (spec 11.3, P11). Money: `*_minor` (kuruş)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import CategoryKey

BudgetState = Literal["OK", "WARNING", "OVER"]

# 10 million TRY: far above any real monthly limit, far below the BIGINT range.
MAX_LIMIT_MINOR = 1_000_000_000


class BudgetIn(BaseModel):
    category_key: CategoryKey
    monthly_limit_minor: int = Field(gt=0, le=MAX_LIMIT_MINOR)


class BudgetOut(BaseModel):
    """One category's limit and its use in a month (spending view, net of refunds)."""

    category_key: CategoryKey
    label: str
    monthly_limit_minor: int
    spent_minor: int
    # Whole percent, rounded down (85 for 85.9 %); never below 0.
    pct: int
    # OK below 80 %, WARNING from 80 %, OVER from 100 %.
    state: BudgetState


class BudgetsOut(BaseModel):
    month: str  # YYYY-MM
    budgets: list[BudgetOut]
