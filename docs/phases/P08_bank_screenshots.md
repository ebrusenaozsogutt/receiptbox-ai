# P08 — Bank Screenshot Import

**Goal:** A masked bank screenshot becomes a reviewable list of rows; confirmed rows become transactions (matching comes in P09).
**Depends on:** P07 · **Week:** 7
**Blocked by:** decision O-001 (which banks) and the owner's masked sample screenshots.
**Read first:** spec §5.5, §15.1, §16 (Extraction)

## Scope

1. Bank detection on device: keyword table per supported bank (2–3 banks from O-001) → `bank_hint`; user can change it in the review screen ("Banka: ▾").
2. `POST /extract/bank-screenshot` {masked_text, bank_hint?, capture_date} → `AIProvider.extract_bank_rows` (implement in Gemini + Fake) with prompt `bank_rows.v1.md` + optional `prompts/banks/<bank>.md` hints → `BankRowExtraction[]`.
3. Row validation: amount string present in text; merchant not a mask token; DEBIT/CREDIT sign rules; drop header/total/balance lines.
4. `app/services/date_resolver.py`: resolve `Bugün`, `Dün`, weekday names, `12 Kasım`, `12.11`, `12/11/2026` using `capture_date` (year inference: never in the future).
5. Parse installment markers in merchant/description: `2/6`, `(2/6)`, `2/6 TAKSİT`, `TAKSİT 2/6`, `6 TAKSİT` → `installment_seq`, `installment_count` (store only; logic in P10).
6. Each row → observation `source=BANK_SCREENSHOT`, `PENDING_REVIEW`, `bank_key`, fingerprint (spec §7.2).
7. Bulk confirm endpoint: `POST /observations/confirm-batch` {ids[], edits{}} → transactions for DEBIT rows; CREDIT rows are kept as observations flagged "possible refund" (handled in P12).
8. Masked text retention: null `masked_text` older than 30 days (startup cleanup task).
9. Mobile: Bank import review screen — list of rows (merchant, amount, date, category chip, installment badge "2/6", pending badge), select/deselect, edit row, "Seçilenleri Kaydet". Image is discarded after OCR (assert in code: no upload call for BANK_SCREENSHOT).

## Out of scope

Matching with receipts (P09), installment logic (P10), refunds (P12), statement PDFs (stretch).

## Acceptance criteria

- [x] For each supported bank, ≥ 3 masked sample texts produce correct rows (fixtures with expected output).
- [x] Relative dates resolved correctly (tests incl. year boundary: capture 2 Jan, row "30 Aralık" → previous year).
- [x] Installment markers parsed in ≥ 8 variants.
- [x] Uploading the same screenshot twice creates no new confirmed rows (fingerprint → `DUPLICATE`).
- [x] No image bytes of bank screenshots reach the backend (test/inspection note).

## Tests

`test_date_resolver.py`, `test_installment_marker.py`, `test_bank_row_validation.py`, `tests/api/test_extract_bank.py` (Fake fixtures).

## Manual check for the owner

Import 3 real screenshots from each bank; compare row count and amounts with the bank app.
