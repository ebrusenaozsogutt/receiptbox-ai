# P12 — Products, Warranties, Return Windows, Refunds

**Goal:** Durable purchases become tracked products with warranty/return deadlines and documents; refunds (full/partial) adjust spending and close return windows.
**Depends on:** P11 · **Week:** 11
**Read first:** spec §6.1 (products, warranties, return_windows, documents), §9, §10

## Scope

### Backend
1. Products CRUD: `GET/POST /products`, `GET/PATCH/DELETE /products/{id}`; create from transaction or receipt item (prefill name/price/date/merchant) or manually.
2. `GET /products/suggestions` — confirmed transactions/items ≥ `PRODUCT_SUGGEST_MIN_MINOR` (default 100000) in TECHNOLOGY/HOME/CLOTHING without a product, not dismissed (store dismissals).
3. Warranty `PUT /products/{id}/warranty`; on product creation propose default end = purchase + 2 years, `source=LEGAL_DEFAULT`, `confirmed=false` until the user accepts/edits.
4. Return window `PUT /products/{id}/return-window`; ONLINE → default purchase + 14 days (`LEGAL_DEFAULT`); IN_STORE/UNKNOWN → none unless user enters (`STORE_POLICY`/`USER`); status auto `CLOSED` after end date.
5. Refunds: `POST /transactions/{id}/refund` {amount_minor (≤ remaining), date, product_id?} → REFUND transaction; product → RETURNED, return window → RETURNED; deletes pending reminders for that product.
6. Bank CREDIT rows (from P08): suggest refund link (same merchant, amount ≤ original remaining, within 60 days) → `POST /observations/{id}/link-refund` {transaction_id}.
7. Financing cost on product detail = plan.total_payable − transaction.total (if plan exists).
8. Feed `analytics/home.attention` with returns ≤ 7 days and warranties ≤ 30 days.

### Mobile
9. Products tab with filter chips and a "Teknoloji Kasam" section (TECHNOLOGY products sorted by warranty days left).
10. Product detail card per spec §10.3 (source labels shown, e.g. "Yasal asgari süre (2 yıl) — düzenleyebilirsin"); actions: Belgeyi Gör, İade Edildi, Düzenle, Arşivle; add warranty document (upload, type WARRANTY).
11. After confirming a qualifying purchase → bottom sheet "Bunu ürün olarak takip edelim mi?" (Evet / Hayır, bir daha sorma).
12. Refund dialog (full/partial) from transaction or product.

## Out of scope

Service history, repair analysis (stretch / future).

## Acceptance criteria

- [ ] Qualifying receipt → product suggestion → product with warranty (LEGAL_DEFAULT, unconfirmed) and correct return window per channel.
- [ ] Partial refund reduces that month's spending by the refunded amount only; full refund marks product RETURNED.
- [ ] Bank CREDIT row suggested as refund of the right purchase.
- [ ] Attention list on Home shows a return ending in 2 days and a warranty ending in 20 days.
- [ ] Isolation tests for products/warranties/returns/refunds.

## Tests

`test_product_suggestions.py`, `test_warranty_defaults.py`, `test_refunds.py`, `tests/api/test_products.py`.

## Manual check for the owner

Create a product from a real electronics receipt; set a return window that ends tomorrow; check Home attention list; mark it returned.
