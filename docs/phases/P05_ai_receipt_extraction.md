# P05 — AI Provider Layer & Receipt Extraction

**Goal:** `POST /extract/receipt` turns masked receipt text into a validated `ReceiptExtraction` with per-field confidence, stored as a `PENDING_REVIEW` observation.
**Depends on:** P01, P04 (payload format) · **Week:** 4
**Read first:** spec §5.2, §5.3, §5.4, §14

## Scope

1. `app/ai/provider.py`: `AIProvider` Protocol (spec §14) + `get_provider()` from settings.
2. `app/ai/providers/gemini.py`: `extract_receipt` using JSON-schema constrained output; model from `AI_MODEL_EXTRACT`; 1 retry on invalid schema; back-off on 429; timeout 30 s. (`extract_bank_rows`, `classify_category`, `run_assistant` raise `NotImplementedError` for now.)
3. `app/ai/providers/fake.py`: `FakeProvider` returning fixtures keyed by a hash of the input text; used by all tests.
4. Prompts: `app/ai/prompts/receipt_extract.v1.md` (rules: copy exactly, null when absent, no arithmetic, Turkish receipt conventions: `TOPLAM`, `TOPKDV`, `*` prefixes, `KDV` lines are not items, `NAKİT/KREDİ KARTI` lines, `TAKSİT SAYISI`). Prompt version saved with the observation.
5. `app/ai/validation.py`: all checks in spec §5.3 → per-field confidence (spec §5.4). Reject extraction when amount insane.
6. `app/services/extraction_service.py`: builds the observation (`source=RECEIPT`, amounts in minor units, `receipt_items`, `extraction_json`, `field_confidence_json`, `masked_text`, `fingerprint` placeholder computed per spec §7.2 formula).
7. Endpoint `POST /extract/receipt` {masked_text, capture_date, source} → `{observation_id, extraction, confidence}`; rate-limited (20/min/user); text size ≤ 20 KB.
8. Call logging: provider, model, prompt version, latency, tokens — no content.
9. Fixtures: ≥ 10 masked receipt texts (the owner provides real ones, anonymised; otherwise realistic synthetic ones) with expected extractions in `tests/fixtures/receipts/`.

## Out of scope

QR path, merchant normalisation, categorisation (P06), mobile review UI (P07).

## Acceptance criteria

- [x] With `AI_PROVIDER=fake`, endpoint returns fixture extraction + correct confidence for all fixtures. *(13 fixtures, `tests/api/test_extract_receipt.py`.)*
- [x] Validation unit tests cover every rule (pass and fail).
- [x] Missing date in text → `date=null`, LOW (never guessed). *(Also when the model invents a date: it is dropped.)*
- [x] With a real Gemini key (manual run), 5 real receipts extract with sensible results; latency logged. *(5 SYNTHETIC receipts, as agreed with the owner; real receipt texts are not available yet. See PROGRESS.)*
- [x] No provider import outside `app/ai/providers/` (enforced by a test that greps imports). *(`test_no_provider_leak.py`, one exempt test file, see P-046.)*

## Tests

`test_validation.py`, `test_extraction_service.py`, `tests/api/test_extract_receipt.py`, `test_no_provider_leak.py`.

## Manual check for the owner

Swagger: paste a masked receipt text from the P04 debug screen; inspect the JSON and confidence.
