# P07 — Receipt Review Flow, Manual Entry, Documents

**Goal:** End-to-end on the phone: capture → review → confirm → a transaction exists; manual entry; receipt images stored privately. **Milestone M1.**
**Depends on:** P04, P05, P06 · **Weeks:** 5–6
**Read first:** spec §5.4, §6.1 (transactions, observations, documents), §6.3, §15.2 (documents), §16 (Observations, Transactions, Documents)

## Scope

### Backend
1. `POST /observations/{id}/confirm` {edited fields: merchant_display, date, time, total, category_key, channel, items[], remember_category_for_merchant?} → creates `transactions` row (kind PURCHASE, payment_type SINGLE unless installment_count>1 → leave a flag for P10), links observation (`CONFIRMED`), saves user category rule if requested. *Matching is NOT run yet (P09 adds it).*
2. `POST /observations/{id}/reject`; `GET /observations?status=PENDING_REVIEW`.
3. Transactions: `GET /transactions` (filters: date range, category, merchant, text search, pagination), `GET /transactions/{id}` (with observations/evidence + items + documents), `PATCH`, `DELETE` (soft), `POST /transactions` (manual; creates a `MANUAL` observation + transaction).
4. Documents: `StorageBackend` interface + `LocalStorage` (`STORAGE_ROOT/users/<user_id>/<uuid>`); `POST /documents` (multipart, jpeg/png/pdf, ≤ 10 MB, sha256), `POST /documents/{id}/access-token` (5-min signed token bound to doc id + user), `GET /documents/{id}/content?token=`, `DELETE`.
5. Cross-user isolation tests for every endpoint above.

### Mobile
6. Receipt review screen: merchant, date, total, category (dropdown, 13 options), channel (Mağaza/Online), items list (editable, collapsible); MEDIUM/LOW fields show "Kontrol et" badge; "Kaydet" / "Vazgeç". Loading state while extracting; on `EXTRACTION_FAILED` open manual form prefilled with what is known.
7. After saving a category change: dialog "Bu mağaza için hep böyle olsun mu?".
8. If "Fiş görsellerini sakla" is on, upload the receipt image (never bank screenshots) and attach to the transaction.
9. Transactions list (grouped by day, filters) and detail screen (evidence chips: Fiş / e-Fatura / Banka / Manuel; document thumbnail opens viewer via access token).
10. Manual entry form (merchant, amount, date, category, note).

## Out of scope

Matching/merge, installments UI, products, refunds.

## Acceptance criteria

- [x] Photograph a receipt → review → save → appears in Harcamalar with correct amount and category, image viewable. _(checked on the emulator with a gallery receipt; the real camera on a phone is still to be checked by the owner)_
- [x] QR invoice path works end-to-end.
- [x] Manual entry works.
- [x] Editing category with "hep böyle olsun" → next receipt from same merchant auto-categorised.
- [x] User B cannot access user A's observation/transaction/document (404) — tests.
- [x] Document token expires after 5 minutes and is single-document.

## Tests

API tests for confirm/reject/transactions/documents + isolation suite; widget test for review screen badges.

## Manual check for the owner

Scan 5 different receipts on the phone and fix one wrong field each time; verify list totals by hand.
