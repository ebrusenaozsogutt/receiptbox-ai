# P09 — Transaction Matching Engine (1:1)

**Goal:** The same purchase seen as a receipt and as a bank row is merged (auto ≥ 95 with undo, suggested 70–95), never double-counted; merges are reversible and logged.
**Depends on:** P07, P08 · **Week:** 8
**Read first:** spec §6.3, §7 (entire)

## Scope

1. `app/matching/features.py`: amount, date, merchant, time feature functions (spec §7.3) + renormalisation for missing features. Pure, fully unit-tested.
2. `app/matching/candidates.py`: candidate generation (same user, |Δdate| ≤ 3 days, |Δamount| ≤ 2%, transaction has no confirmed observation of the same source, not deleted, kind PURCHASE).
3. `app/matching/engine.py`: `evaluate(observation) → MatchResult` = exact duplicate → (k/n marker → defer to P10 hook, return "installment") → candidates → scores → decision per thresholds (config `MATCH_AUTO=95`, `MATCH_SUGGEST=70`). Every evaluated candidate ≥ 50 is written to `match_decisions` with `features_json`.
4. Integration: run on observation confirm (receipt, QR, bank, manual). Auto-accept → attach observation to existing transaction instead of creating a new one. Pending → create **no** new transaction until the user decides; observation stays `PENDING_REVIEW` with a suggestion.
5. Merge field precedence (spec §7.5); keep bank amount as evidence only.
6. Endpoints: `GET /matches?decision=PENDING`, `POST /matches/{id}/accept`, `POST /matches/{id}/reject` (→ create new transaction), `POST /transactions/{id}/unmerge` {observation_id} (→ restore; decision `UNDONE`).
7. Mobile: match suggestion sheet ("Bu işlem daha önce eklediğin Migros fişiyle aynı olabilir. Birleştirilsin mi?" with side-by-side evidence); toast with **Geri al** after auto-merge; in bank import review show badge "Eşleşti" / "Olası eşleşme"; in transaction detail "Ayır" (unmerge) per evidence.

## Out of scope

Installment matching (P10), ML scorer (P15 compares it offline).

## Acceptance criteria

- [x] Receipt (18:27) + bank row (18:28, `MIGROS TICARET AS`, same amount) → auto-merged; spending counts once.
- [x] Two identical coffees same day from the bank → two transactions (same-source rule) — test.
- [x] Receipt + bank row with 1-day date shift and no time → suggestion, not auto.
- [x] Unmerge restores two transactions; totals correct; decision logged `UNDONE`.
- [x] Order independence: bank first then receipt gives the same result as receipt first.
- [x] Feature functions: ≥ 30 unit tests; engine: ≥ 12 scenario tests.

## Tests

`test_match_features.py`, `test_match_engine_scenarios.py`, `tests/api/test_matches.py`, isolation tests for match endpoints.

## Manual check for the owner

Import a bank screenshot, then scan two receipts of those purchases; watch the merge/undo behaviour; check monthly total unchanged.
