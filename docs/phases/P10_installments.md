# P10 — Installments (1:N Matching)

**Goal:** One installment purchase = one spending + N payments; bank installment rows attach to payments, never adding spending. **Milestone M2.**
**Depends on:** P09 · **Week:** 9
**Read first:** spec §6.1 (installment tables), §6.3, §8 (entire)

## Scope

1. `app/services/installment_service.py`:
   - `create_plan(transaction, n, first_due_month?, total_payable?)` — rounding: equal parts, last absorbs remainder; default first_due_month = purchase month + 1.
   - `PUT /transactions/{id}/installment-plan` (create/replace), `PATCH /installment-plans/{id}` (status CANCELLED, first_due_month, total_payable).
   - Auto-create plan on confirm when extraction has `installment_count > 1` or bank row has a total with "n taksit".
2. `app/matching/installment_matcher.py` (spec §8.2): candidate plans (merchant sim ≥ 0.8, count = n, amount tolerance max(100 kuruş, 1%), due month of payment k within ±1 month) → link observation to payment k (`OBSERVED`), earlier EXPECTED → `INFERRED`.
3. No candidate → estimated purchase (`is_estimated=true`, total = n × amount, date ≈ row date − (k−1) months), plan, payments statuses per spec. Later receipt with matching total merges via P09 engine and clears `is_estimated` (corrects date/total from receipt).
4. Marker-less suggestion (spec §8.3) → `match_decisions` with `match_type=INSTALLMENT`, PENDING only.
5. Plan status job on startup/daily call: ACTIVE → COMPLETED after last due month.
6. `GET /installments/schedule?from=&to=` → months with payment lists, totals, remaining total.
7. Mobile: "Taksitli" toggle + count on review/manual/detail screens; installment section in transaction detail (6 dots: observed/inferred/expected); Installments schedule screen; bank import row badge "Taksit 2/6 → MediaMarkt alışverişine bağlandı".

## Out of scope

Automatic cancellation detection, interest calculation beyond `total_payable − total`.

## Acceptance criteria

- [ ] Receipt 12.499 TL with 6 installments + bank rows 1/6…3/6 → spending 12.499 once in purchase month; payments view shows 2.083,17×5 + 2.083,15 (rounding) by month.
- [ ] Bank row 2/6 first (no receipt) → estimated purchase; receipt later merges; estimated flag cleared; no double count.
- [ ] Marker-less row equal to total/6 → suggestion only.
- [ ] Rounding: Σ payments = total for n = 2..12 (property test).
- [ ] Schedule endpoint correct across year boundary.

## Tests

`test_installment_rounding.py` (property), `test_installment_matcher.py` (≥ 12 scenarios), `tests/api/test_installments.py`.

## Manual check for the owner

Use a real installment purchase of yours: scan the slip, import the bank rows of two months, check both views.
