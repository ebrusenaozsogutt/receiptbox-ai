# P16 — Hardening, Security Tests, Demo

**Goal:** A stable, secure, demo-ready release APK and a scripted jury demo. **Milestone M4.**
**Depends on:** P15 · **Week:** 14
**Read first:** spec §15, §20, `docs/PROGRESS.md` (known gaps)

## Scope

1. **Security pass:** automated isolation suite across *all* endpoints (generated from the OpenAPI spec: every `{id}` route called as another user → 404); auth edge cases; upload MIME/size limits; rate limits; log audit (grep logs from a full test run for OCR text, e-mails, tokens → must be none).
2. **Robustness:** LLM timeout/429/invalid-output paths show manual-entry fallbacks in the app; backend returns stable error codes; app handles no-network gracefully (clear message, retry).
3. **Demo data:** `scripts/seed_demo.py` creates a demo user with 3 months of realistic data (receipts, bank rows, merges, an installment plan, products with near deadlines, budgets). Reset command.
4. **Demo script** `docs/DEMO.md` (Turkish, step by step, ~7 minutes): bank screenshot → auto rows → scan the same receipt → "Mevcut banka işlemiyle eşleşti" → installment row attaches → MediaMarkt receipt → product + warranty → Home (spending + due this month) → assistant questions ("Bu ay teknolojiye ne kadar harcadım?", "Garantisi yakında bitecek ne var?", "Kalan taksitlerim?"). Include a fallback path using seeded data if live OCR fails.
5. **Release build:** signed release APK (keystore kept out of git; instructions in README), app icon/name "ReceiptBox", version 1.0.0; backend run instructions for the demo laptop (Docker Compose) and phone on the same Wi-Fi.
6. **Docs:** README final; `docs/ARCHITECTURE.md` (diagram + module overview, generated from code reality); update spec only via DECISIONS if reality differs.
7. Fix all "known gaps" in PROGRESS that are in scope.

## Out of scope

Play Store publishing, cloud deployment (documented as future work), any new feature.

## Acceptance criteria

- [ ] Isolation suite covers 100% of user-data routes and passes.
- [ ] Log audit finds no sensitive content.
- [ ] Demo script runs end-to-end twice in a row on a real phone with fresh seed.
- [ ] Release APK installs and runs against the demo backend.
- [ ] CI green; PROGRESS shows all phases ✅.

## Tests

`tests/security/test_isolation_all_routes.py`, `tests/security/test_log_audit.py`, smoke test for `seed_demo.py`.

## Manual check for the owner

Rehearse the demo with a timer; ask a friend to try the app for 10 minutes and note confusing points.
