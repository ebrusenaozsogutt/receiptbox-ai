# P06 — e-Invoice QR, Merchant Normalisation, Categorisation

**Goal:** QR-first extraction path, canonical merchants and automatic categories for every observation.
**Depends on:** P05 · **Week:** 5
**Read first:** spec §5.1 (QR), §5.6, §5.7

## Scope

1. `app/qr/gib_qr.py`: tolerant parser for GİB QR JSON (unknown keys ignored; `odenecek` → total, fallback `vergidahil`; `tarih` → date (multiple formats); `ettn` → external_id; seller `vkntckn` kept only for merchant lookup; buyer IDs discarded). Returns a `ReceiptExtraction` with all present fields HIGH.
2. `POST /extract/einvoice-qr` {qr_payload, masked_text?, capture_date} → observation `source=EINVOICE_QR`. If `masked_text` is present, items may be extracted via LLM; header fields always come from QR.
3. `app/matching/merchant_normalizer.py`: steps 1–5 of spec §5.6 (Turkish-aware casing, suffix stripping, alias lookup user→global, rapidfuzz ≥ 90, create new). Pure functions + repository calls separated.
4. `app/services/categorization_service.py`: user rule → merchant default → `AIProvider.classify_category` (implement in Gemini + Fake; constrained to the 13 keys) → `OTHER` on failure.
5. Hook both into `extraction_service` so every observation gets `merchant_id` suggestion + `category` suggestion (stored in `extraction_json.suggestions`).
6. Mobile: when `CapturePayload.qr_payload` exists, call `/extract/einvoice-qr` instead of `/extract/receipt`.

## Out of scope

Creating user rules from the UI (P07), bank rows (P08).

## Acceptance criteria

- [ ] QR parser tests with ≥ 6 payload variants (comma/dot decimals, missing fields, extra fields, malformed JSON → clear error).
- [ ] Normaliser tests: ≥ 25 real-looking variants (`MIGROS TICARET AS`, `MİGROS SANAL MARKET`, `MIGROS MAGAZACILIK 1234 KONYA`, `A101 YENI MAGAZACILIK`, `SHELL&TURCAS`, `TRENDYOL.COM`, `STARBUCKS COFFEE`) map to the right canonical merchant.
- [ ] Categoriser precedence tested (user rule beats default beats LLM).
- [ ] A QR-only invoice creates an observation with no LLM call (asserted via FakeProvider call counter).

## Tests

`test_gib_qr.py`, `test_merchant_normalizer.py`, `test_categorization.py`, `tests/api/test_extract_einvoice.py`.

## Manual check for the owner

Scan the QR on a real e-Archive invoice from an online order; confirm merchant, date, total are exact.
