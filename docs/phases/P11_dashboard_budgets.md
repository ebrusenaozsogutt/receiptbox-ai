# P11 — Dashboard, Analytics, Budgets

**Goal:** The home screen in its fixed order plus analytics and budgets, all computed by SQL.
**Depends on:** P10 · **Week:** 10
**Read first:** spec §6.3 (spending vs payments), §11 (entire)

## Scope

### Backend (`app/services/analytics.py`, SQL only)
1. `GET /analytics/home?month=YYYY-MM` → `{spending: {total, by_category[], prev_month_total, change_pct}, attention: [...returns ≤7d, warranties ≤30d, budgets ≥80%], due_this_month: {total, payments[]}, next_months: [{month, total}×6]}`. (Attention items for returns/warranties return empty until P12 — keep the shape.)
2. `GET /analytics/spending?from&to&group_by=category|merchant|month|week` — net of refunds (refund rows reduce the original month).
3. `GET /analytics/compare?a_from&a_to&b_from&b_to` → totals, delta, top 3 contributing categories.
4. `GET /analytics/year?year=` → total, by category, by month, top merchants.
5. Optional AI commentary `GET /analytics/compare/commentary` — prompt receives **only** the computed numbers; output ≤ 2 sentences; cached per user+period.
6. Budgets: `GET/PUT /budgets`, `DELETE /budgets/{category_key}`; usage computed on spending view; threshold crossing creates BUDGET_80/BUDGET_100 reminders (consumed in P13).

### Mobile
7. Home screen (order fixed): Spending card (total, change %, category bars) → "Dikkat gerektirenler" → "Bu ay ödenecekler" (total, list, 6-month mini chart with `fl_chart`). Month switcher.
8. Analytics screen (from Harcamalar tab): week/month/year segmented control, category and merchant breakdowns, comparison card with AI commentary.
9. Budgets screen: per-category limit, progress bars (≥80% warning color).

## Out of scope

Exports, custom date-range charts beyond the above, subscriptions.

## Acceptance criteria

- [x] SQL results equal a Python reference calculation on a seeded dataset (≥ 200 transactions incl. refunds and installments) — test.
- [x] Installment payments never appear in spending totals; appear in due-this-month.
- [x] Commentary prompt contains no raw transactions, only aggregates (test inspects prompt).
- [x] Budget 80%/100% reminders created exactly once per category per month.
- [x] Home loads < 500 ms on seeded data locally.

## Tests

`test_analytics_sql.py` (reference comparison), `test_budgets.py`, `tests/api/test_analytics.py`, home widget test.

## Manual check for the owner

Compare the home numbers with your own manual sum for one month of your real data.
