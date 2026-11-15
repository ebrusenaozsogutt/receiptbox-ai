---
name: receiptbox-scope
description: Scope guard for ReceiptBox AI. Use before planning, implementing, reviewing or extending any ReceiptBox feature to check what is in scope, what is forbidden, the data invariants and the phase order.
---

# ReceiptBox AI — Scope Guard

ReceiptBox AI is an **Android** app that remembers what the user bought and the money/product life cycle of those purchases. Single-semester senior design project; solo owner; Claude Code writes the code.

Use this skill to answer one question before every change: **"Is this inside the agreed scope, and does it respect the invariants?"** If the answer is not a clear yes, stop and ask the owner. Do not "helpfully" add features.

## 1. In scope (MVP — must ship)

1. Email/password auth (Argon2id, JWT 15 min + rotating refresh 30 days), 18+ confirmation checkbox.
2. Capture: camera, gallery, Android share sheet (images + PDFs).
3. On-device OCR (ML Kit) and **on-device PII masking** before upload.
4. GİB e-Archive/e-Invoice **QR-first** parsing.
5. LLM structured extraction (receipts, bank screenshots) + deterministic **validation** + HIGH/MEDIUM/LOW **confidence**.
6. Merchant normalisation; hybrid categorisation (user rule → merchant default → LLM); fixed 13 categories.
7. Review screen for every extraction.
8. Bank screenshot import for 2–3 banks (chosen from the owner's samples).
9. Matching engine: exact duplicates, 1:1 cross-source merge (score thresholds 95/70), unmerge.
10. Installments: plans, k/n bank-row matching, estimated purchases, payments-due view.
11. Manual purchases; full/partial refunds.
12. Products (suggested at ≥ 1,000 TRY in TECHNOLOGY/HOME/CLOTHING), warranties (default +2 years, LEGAL_DEFAULT), return windows (ONLINE default +14 days; IN_STORE asks user), documents (private storage, 5-min tokens).
13. Home: spending (top) → needs attention → due this month (bottom); comparisons; yearly view; budgets (80/100% alerts).
14. Local notifications (warranty, return, last installment, budget). No server push.
15. AI assistant with the 8 typed tools from spec §13.2; Turkish answers; deep-link actions.
16. Evaluation harness E1–E4 (spec §19).
17. Account deletion.

## 2. Stretch — only after P16 is done AND the owner explicitly approves

Subscription detection · service history / total cost of ownership · e-statement PDF import · personal inflation index.

## 3. Out of scope — never implement

- Bank APIs/open banking, investments, crypto, credit score, loans, accounting, business invoicing, in-app payments.
- iOS, web, desktop, admin panel.
- Household/family sharing, RAG, embeddings/pgvector, email inbox integration, repair-vs-replace analysis, social, marketplace, multi-currency conversion, training OCR models.
- Offline sync queue, FCM/server push, Redis, Celery/ARQ, Kubernetes, microservices, Prometheus/Grafana.
- Storing full card numbers, IBANs, balances, TCKN, or any bank screenshot image off-device.

**Anything not listed in §1 or §2 is out of scope.** Write it to `docs/DECISIONS.md` → "Proposed / not approved" and ask.

## 4. Invariants (must always hold)

1. Money = integer minor units (kuruş). No floats.
2. Every user-data query filters by `user_id`; `user_id` is never an LLM tool argument.
3. The LLM never produces numbers that are shown as facts; SQL/Python computes them.
4. Observations are evidence; transactions are canonical. Merges are reversible and logged in `match_decisions`.
5. A purchase has at most one confirmed observation per source (except bank rows linked via installment payments).
6. Installment payments never add to spending. Spending view = purchases in purchase month (net of refunds). Payments view = installments by due month.
7. Unknown dates/warranties are left empty or proposed with an explicit source label — never silently invented.
8. Bank screenshot images never leave the phone; all uploaded text is masked; logs contain no OCR text.
9. Provider SDKs only in `backend/app/ai/providers/`; tests use `FakeProvider`.
10. UI Turkish; code and docs English.

## 5. Phase order (one at a time; owner approves each)

P00 bootstrap → P01 data model → P02 auth → P03 mobile shell → P04 capture/OCR/QR/masking → P05 AI layer & receipt extraction → P06 QR, merchants, categories → P07 receipt review & documents → P08 bank screenshots → P09 matching 1:1 → P10 installments → P11 dashboard & budgets → P12 products/warranty/returns/refunds → P13 reminders → P14 assistant → P15 evaluation → P16 hardening & demo.

## 6. Decision checklist before writing code

- [ ] Which phase is this? Is the task listed in that phase file?
- [ ] Does it touch an out-of-scope area (§3)? → stop.
- [ ] Does it break an invariant (§4)? → stop.
- [ ] Are tests planned (unit + cross-user isolation where data is involved)?
- [ ] Will `docs/PROGRESS.md` be updated?

## 7. Where things are

- Spec: `docs/spec/00_PROJECT_SPEC.md` · Phases: `docs/phases/` · Decisions: `docs/DECISIONS.md` · Progress: `docs/PROGRESS.md` · Design: `docs/design/DESIGN_TRACK.md`.
