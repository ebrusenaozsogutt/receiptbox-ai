# ReceiptBox AI — Project Specification

> **Status:** v1.0 (frozen for implementation) · **Owner:** Ebru Sena Özsöğüt · **Type:** Single-semester senior design project (Computer Engineering, KTO Karatay University)
>
> This document is the single source of truth for *what* is built. Phase files in `docs/phases/` describe *how and in which order*. If anything here conflicts with a phase file, **this document wins**; record the conflict in `docs/DECISIONS.md` and ask the owner.

---

## Table of Contents

1. [Product Definition](#1-product-definition)
2. [Users and Core Use Cases](#2-users-and-core-use-cases)
3. [Scope](#3-scope)
4. [System Architecture](#4-system-architecture)
5. [Capture & Understanding Pipelines](#5-capture--understanding-pipelines)
6. [Data Model](#6-data-model)
7. [Transaction Matching Engine](#7-transaction-matching-engine)
8. [Installments (1:N Matching)](#8-installments-1n-matching)
9. [Refunds](#9-refunds)
10. [Products, Warranties, Returns](#10-products-warranties-returns)
11. [Analytics, Dashboard, Budgets](#11-analytics-dashboard-budgets)
12. [Reminders & Notifications](#12-reminders--notifications)
13. [AI Assistant (Purchase Memory)](#13-ai-assistant-purchase-memory)
14. [AI Provider Layer](#14-ai-provider-layer)
15. [Privacy & Security](#15-privacy--security)
16. [API Overview](#16-api-overview)
17. [Mobile App Structure & Screens](#17-mobile-app-structure--screens)
18. [Tech Stack](#18-tech-stack)
19. [Research & Evaluation Plan](#19-research--evaluation-plan)
20. [Testing Strategy](#20-testing-strategy)
21. [Repository Layout](#21-repository-layout)
22. [Implementation Phases (summary)](#22-implementation-phases-summary)
23. [Glossary](#23-glossary)

---

## 1. Product Definition

**ReceiptBox AI** is an AI-powered Android app that acts as a *personal purchase memory*. It:

- extracts purchases automatically from **receipt photos**, **e-Archive/e-Invoice QR codes** and **mobile-banking screenshots**;
- **merges** the same purchase seen from different sources (receipt + bank) so nothing is double-counted, including **installment** purchases;
- analyses spending (monthly/yearly, by category, budgets) and shows **what is due this month**;
- tracks the **life cycle of long-lived products**: warranty, return window, documents;
- lets the user **query their own purchase history in natural language**, where the LLM answers only from database results obtained through tool calls.

**Identity statement (do not drift from this):** *A system that remembers what you bought and the money/product life cycle of those purchases.*

### 1.1 The three original technical contributions

1. **Cross-source transaction reconciliation:** receipt ↔ bank screenshot matching, both 1:1 (duplicates) and 1:N (installments).
2. **Tool-grounded purchase memory:** natural-language questions answered by an LLM that must call typed backend tools; it never invents numbers.
3. **Unified spending + product life-cycle data model:** a purchase is a transaction *and* (optionally) a tracked product with warranty/return deadlines.

### 1.2 Two memories, one assistant

```
                 RECEIPTBOX AI
                      │
        ┌─────────────┴─────────────┐
  SPENDING MEMORY             PRODUCT MEMORY
  (transactions, payments)    (products, warranties, returns, documents)
        └─────────────┬─────────────┘
                AI ASSISTANT
```

---

## 2. Users and Core Use Cases

**Target users:** adults (18+), young to middle-aged, Turkish-speaking, Android users who pay with cards and often buy in installments. The app UI is **Turkish**; code, comments and docs are **English**. Users must confirm they are 18+ at registration (checkbox). No parental-consent flow.

| ID | Use case |
|---|---|
| UC1 | Photograph a receipt → review extracted merchant/date/total/items → save as a purchase. |
| UC2 | Scan/share an e-Archive invoice (PDF or photo with GİB QR) → purchase created from QR data with no LLM. |
| UC3 | Import a bank-app screenshot → several rows extracted → confirm → purchases created or matched. |
| UC4 | System detects that a bank row and a receipt are the same purchase → user confirms merge (or it auto-merges with undo). |
| UC5 | Bank row "TRENDYOL 2/6" is recognised as installment 2 of 6 of an existing purchase; no new spending is created. |
| UC6 | Add a purchase manually (cash, no receipt). |
| UC7 | Mark a purchase (or part of it) as refunded. |
| UC8 | A purchase ≥ threshold in a durable category is suggested as a **product**; warranty/return defaults are proposed. |
| UC9 | Home screen: this month's spending by category (top) and installments due this month (bottom); "needs attention" list. |
| UC10 | Set monthly category budgets and get alerts at 80% / 100%. |
| UC11 | Receive local notifications before warranty expiry / return deadline / last installment. |
| UC12 | Ask the assistant: "Bu ay markete ne kadar harcadım?", "Garantisi bitecek ne var?", "Kalan taksitlerim ne kadar?", "Kulaklığın faturası nerede?" |
| UC13 | Share a screenshot or PDF from another app (Android share sheet) into ReceiptBox. |

---

## 3. Scope

### 3.1 In scope (MVP — must ship)

- Android app (Flutter), email/password auth.
- Receipt capture: camera, gallery, Android share sheet (images, PDFs).
- On-device OCR (ML Kit) and **on-device PII masking** before any text leaves the phone.
- **GİB e-Archive/e-Invoice QR** parsing (QR-first path).
- LLM-based structured extraction for receipts and bank screenshots + rule-based **validation** + **confidence** levels.
- Merchant normalisation + hybrid categorisation (rules → LLM → user overrides remembered).
- Review screens for every extraction (nothing is saved without user confirmation, except auto-merge ≥ threshold with undo).
- Bank screenshot import for **2–3 Turkish banks** (selected once the owner provides sample screenshots; see `docs/DECISIONS.md`).
- Transaction Matching Engine: exact duplicate detection, cross-source 1:1 matching, installment 1:N matching, merge/unmerge.
- Installment plans and "due this month" view.
- Manual purchases, basic refunds (full/partial).
- Products, warranties, return windows, documents (stored privately, served through short-lived tokens).
- Dashboard (spending view + payments-due view), month-over-month comparison, yearly summary, budgets.
- Local notifications (warranty, return, installment end, budget).
- AI assistant with typed tool calling; answers in Turkish; deep-link actions.
- Evaluation harness and experiments (Section 19).
- Account deletion (deletes all user data and documents).

### 3.2 Stretch (only after Phase P16 is done **and** the owner approves)

Subscription detection & price-increase alerts · service history & total cost of ownership · credit-card e-statement PDF import · "personal inflation" from item-level prices.

### 3.3 Explicitly out of scope (never implement unless the owner changes this document)

| Area | Out of scope |
|---|---|
| Finance | Open-banking / bank APIs, investments, crypto, credit score, loans, accounting, business invoicing, in-app payments |
| Platforms | iOS build, web app, desktop app, admin panel |
| Features | Household/family sharing, RAG over documents, pgvector/embeddings, email-inbox integration, repair-vs-replace analysis, social features, marketplace, multi-currency conversion, receipt OCR model training |
| Infra | Offline sync queue, Firebase Cloud Messaging/push from server, Redis, Celery/ARQ, Kubernetes, microservices, Prometheus/Grafana |
| Data | Storing full card numbers, IBANs, balances, national ID numbers; storing bank screenshot images anywhere off the device |

When something is not listed in 3.1 or 3.2, treat it as **out of scope** and ask.

---

## 4. System Architecture

```
┌──────────────────── Android (Flutter) ────────────────────┐
│ Capture (camera / gallery / share)                         │
│   → QR detect (ML Kit barcode) ──► GİB QR payload           │
│   → OCR (ML Kit text, on-device) → PII Masker (Dart)        │
│   → masked text + QR payload + capture metadata             │
│ Review UIs · Dashboard · Products · Assistant chat          │
│ Local notifications (flutter_local_notifications)           │
└───────────────┬─────────────────────────────────────────────┘
                │ HTTPS + JWT
┌───────────────▼──────────── FastAPI backend ────────────────┐
│ api/ (routers) → services/ (business logic) → repositories/ │
│ ai/       provider interface, prompts, extractors, assistant │
│ matching/ normaliser, scorer, installment matcher            │
│ qr/       GİB QR parser          storage/ local file backend  │
│ reminders/ deadline computation   security/ auth, tokens      │
└───────────────┬─────────────────────────┬──────────────────┘
          PostgreSQL 16              Local file storage (private dir)
                │
         LLM provider (Gemini free tier by default, via AIProvider)
```

**Principles**

1. **SQL for numbers, LLM for language.** Totals, comparisons, deadlines are always computed by SQL/Python. The LLM extracts structure from text and phrases answers.
2. **The phone is the privacy boundary.** Raw images of bank screenshots never leave the device; all text is masked before upload.
3. **Observations are immutable evidence; transactions are the canonical truth.** Merges are reversible.
4. **Human in the loop.** Every extraction is reviewed; uncertain fields are flagged.
5. **Provider-agnostic AI.** No provider SDK is imported outside `backend/app/ai/providers/`.
6. **Keep it small.** A single FastAPI process + PostgreSQL. Long operations are synchronous with timeouts.

---

## 5. Capture & Understanding Pipelines

### 5.1 Receipt / invoice pipeline

```
image/PDF ─► [1] QR detection (ML Kit barcode scanning)
              ├─ GİB e-document QR found ─► send qr_payload ─► backend QR parser
              │                               → Observation(source=EINVOICE_QR, confidence=HIGH)
              │                               (items optional: if OCR text is also sent, LLM may extract items)
              └─ not found
                  ─► [2] OCR (ML Kit text recognition, Latin script)
                  ─► [3] PII masking (on-device)
                  ─► [4] POST /extract/receipt {masked_text, capture_meta}
                  ─► [5] LLM structured extraction (ReceiptExtraction schema)
                  ─► [6] Validation Engine  ─► [7] Confidence  ─► [8] Categorisation
                  ─► Observation(status=PENDING_REVIEW) ─► mobile review screen
```

- **PDFs** (shared e-Archive invoices): render first page(s) to image on device, then the same pipeline. QR first.
- **GİB QR payload:** JSON with fields such as `vkntckn`, `avkntckn`, `senaryo`, `tip`, `tarih`, `no`, `ettn`, `parabirimi`, `malhizmettoplam`, `vergidahil`, `odenecek` and tax lines. Parser must be tolerant (unknown keys ignored, numbers with `.` or `,`). Mapping: `odenecek` → total, `tarih` → date, `ettn` → stored as `external_id` (used for exact-duplicate detection), seller VKN/name → merchant lookup. **Never store the buyer's TCKN** (`avkntckn` is dropped on device before upload).

### 5.2 ReceiptExtraction schema (LLM output)

```python
class ReceiptItem(BaseModel):
    name_raw: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None

class ReceiptExtraction(BaseModel):
    merchant_raw: str | None
    date: date | None            # never guessed; null if absent
    time: time | None
    total: Decimal | None
    currency: str = "TRY"
    payment_method: Literal["CARD", "CASH", "UNKNOWN"] = "UNKNOWN"
    installment_count: int | None   # e.g. POS slip "TAKSİT SAYISI: 6"
    items: list[ReceiptItem] = []
```

The LLM is called with a JSON-schema constrained response. Free-text output is rejected. Prompt rules: *copy values exactly as they appear; return null when a field is absent; do not compute totals.*

### 5.3 Validation Engine (deterministic)

| Check | Rule | Effect |
|---|---|---|
| Total present in text | normalised total string appears in OCR text (accept `494,60`, `494.60`, `*494,60`) | fail → total confidence LOW |
| Items sum | Σ item totals within ±0.05 TRY or ±1% of total (discount lines allowed) | fail → items confidence LOW, total unaffected if check 1 passes |
| Date plausible | parseable, not in the future (>1 day), not older than 5 years, present in text | fail → date set to null + LOW |
| Merchant present | merchant_raw tokens appear in first 8 lines of text | fail → LOW |
| Amount sane | 0 < total < 1,000,000 TRY | fail → reject extraction |

### 5.4 Confidence levels

Per field: `HIGH` (validated), `MEDIUM` (present but one soft check failed / fuzzy), `LOW` (failed or missing). The review UI highlights MEDIUM/LOW with a "Kontrol et" badge. QR-derived fields are HIGH. No numeric "probabilities" are shown to users.

### 5.5 Bank screenshot pipeline

```
screenshot ─► OCR on device ─► PII masking ─► bank detection (keywords; user can override)
           ─► POST /extract/bank-screenshot {masked_text, bank_hint, capture_date}
           ─► LLM extraction → BankRowExtraction[] ─► per-row validation
           ─► relative date resolution ("Bugün", "Dün", weekday names) using capture_date
           ─► installment marker parsing (k/n) ─► matching suggestions ─► review list
```

```python
class BankRowExtraction(BaseModel):
    merchant_raw: str
    amount: Decimal                     # always positive
    direction: Literal["DEBIT", "CREDIT"]   # CREDIT = refund/incoming
    date_text: str | None               # as written ("Bugün", "12 Kasım")
    time: time | None
    installment_seq: int | None         # k in "k/n"
    installment_count: int | None       # n in "k/n"
    is_pending: bool = False            # "provizyon"/"bekleyen" if shown
```

- Validation: each amount string must appear in the masked text; rows whose merchant text is a masked token are dropped.
- **The screenshot image is never uploaded or stored.** Only masked text is sent; only extracted fields are persisted (masked raw text is kept for 30 days for debugging, then nulled by a cleanup job run at startup).
- Overlapping screenshots (same rows twice) are handled by exact-duplicate detection (Section 7.2).
- Supported banks: decided after sample collection (target: the owner's own banks, 2–3). Bank-specific hints live in `backend/app/ai/prompts/banks/<bank>.md`.

### 5.6 Merchant normalisation

1. Turkish-aware uppercase (`i→İ`, `ı→I`), strip punctuation, collapse spaces.
2. Remove legal/branch suffixes: `A.Ş., AŞ, TIC., TİC., LTD., ŞTİ., STI, SAN., MAĞAZACILIK, MAGAZACILIK, SANAL MARKET, GIDA, PAZARLAMA, ŞUBE`, trailing store codes/digits, city names list.
3. Look up `merchant_aliases` (user-specific aliases first, then global).
4. Else fuzzy match against canonical names (rapidfuzz `token_set_ratio ≥ 90`).
5. Else create a new merchant (canonical name = cleaned title-case string).

### 5.7 Categorisation (hybrid)

1. User override rule (`user_category_rules`, merchant → category) — always wins.
2. Merchant default category (seeded for ~150 common Turkish merchants: Migros, BİM, A101, ŞOK, CarrefourSA, Starbucks, Shell, Opet, Trendyol, Hepsiburada, MediaMarkt, Teknosa, Vatan, Netflix, Spotify, …).
3. LLM classification (single call, constrained to the category enum) when unknown.
4. When the user changes a category, ask "Bu mağaza için hep böyle olsun mu?" → store a user rule.

**Fixed category set** (keys / Turkish labels): `GROCERY` Market · `FOOD_DRINK` Yeme-İçme · `TRANSPORT` Ulaşım · `FUEL` Yakıt · `CLOTHING` Giyim · `TECHNOLOGY` Teknoloji · `HOME` Ev & Yaşam · `HEALTH_CARE` Sağlık & Kişisel Bakım · `ENTERTAINMENT` Eğlence · `SUBSCRIPTION` Abonelik · `EDUCATION` Eğitim · `BILLS` Fatura & Hizmetler · `OTHER` Diğer.

---

## 6. Data Model

Conventions: UUID primary keys; `created_at`/`updated_at` timestamptz; **money as `BIGINT` minor units (kuruş)** with `currency CHAR(3) DEFAULT 'TRY'`; every user-owned table has `user_id` and every query filters by it (enforced in repositories). Soft delete only where stated.

### 6.1 Tables

| Table | Key columns |
|---|---|
| `users` | id, email (unique, lowercased), password_hash, is_adult_confirmed, created_at |
| `refresh_tokens` | id, user_id, token_hash, expires_at, revoked_at, replaced_by |
| `categories` | id, key (enum above), label_tr, sort_order — seeded, read-only |
| `merchants` | id, canonical_name, default_category_id |
| `merchant_aliases` | id, merchant_id, alias_normalized, user_id NULL (NULL = global) — unique(alias_normalized, user_id) |
| `user_category_rules` | user_id, merchant_id, category_id — PK(user_id, merchant_id) |
| `transactions` *(canonical purchase)* | id, user_id, merchant_id, merchant_display, category_id, purchase_date, purchase_time NULL, total_minor, currency, payment_type `SINGLE/INSTALLMENT`, channel `IN_STORE/ONLINE/UNKNOWN`, kind `PURCHASE/REFUND`, refund_of_id NULL, is_estimated bool, note, deleted_at NULL |
| `observations` *(evidence)* | id, user_id, source `RECEIPT/EINVOICE_QR/BANK_SCREENSHOT/MANUAL`, status `PENDING_REVIEW/CONFIRMED/REJECTED/DUPLICATE`, transaction_id NULL, installment_payment_id NULL, merchant_raw, amount_minor, direction, obs_date, obs_time, installment_seq, installment_count, external_id NULL (ETTN), fingerprint, masked_text NULL, extraction_json, field_confidence_json, bank_key NULL, created_at |
| `receipt_items` | id, observation_id, name_raw, quantity, unit_price_minor, total_price_minor |
| `installment_plans` | id, transaction_id (unique), count, installment_minor, total_payable_minor, first_due_month (date, day=1), status `ACTIVE/COMPLETED/CANCELLED` |
| `installment_payments` | id, plan_id, seq, due_month, amount_minor, status `EXPECTED/OBSERVED/INFERRED` — unique(plan_id, seq) |
| `match_decisions` | id, user_id, observation_id, transaction_id NULL, installment_payment_id NULL, match_type `DUPLICATE/INSTALLMENT`, score, features_json, decision `PENDING/ACCEPTED/REJECTED/AUTO_ACCEPTED/UNDONE`, decided_at |
| `documents` | id, user_id, type `RECEIPT_IMAGE/INVOICE/WARRANTY/OTHER`, storage_key, mime_type, sha256, size_bytes, transaction_id NULL, product_id NULL |
| `products` | id, user_id, transaction_id NULL, receipt_item_id NULL, name, brand, model, serial_number, product_category, purchase_date, purchase_price_minor, status `ACTIVE/RETURNED/ARCHIVED` |
| `warranties` | id, product_id (unique), start_date, end_date, source `DOCUMENT/LEGAL_DEFAULT/USER`, confirmed bool |
| `return_windows` | id, product_id (unique), end_date, source `LEGAL_DEFAULT/STORE_POLICY/USER`, status `OPEN/CLOSED/RETURNED` |
| `budgets` | id, user_id, category_id, monthly_limit_minor — unique(user_id, category_id) |
| `reminders` | id, user_id, type `WARRANTY_EXPIRY/RETURN_DEADLINE/INSTALLMENT_END/BUDGET_80/BUDGET_100`, target_id, fire_at, delivered_at NULL, dismissed_at NULL |
| `assistant_turns` | id, user_id, question, tool_calls_json, answer, actions_json, latency_ms, created_at (for evaluation/debugging; user can clear) |

### 6.2 Key relations

```
transactions 1 ──< observations            (evidence: receipt, QR, bank row, manual)
transactions 1 ──1 installment_plans 1 ──< installment_payments >──1 observations (bank rows)
transactions 1 ──< products 1──1 warranties, 1──1 return_windows
transactions/products 1 ──< documents
transactions(REFUND).refund_of_id ──> transactions(PURCHASE)
```

### 6.3 Invariants

- A `PURCHASE` transaction has **at most one CONFIRMED observation per source**, except bank observations linked through `installment_payments`.
- Spending totals = Σ `transactions.total_minor` where kind=PURCHASE and not deleted, **minus** linked REFUND amounts. Installment payments are **never** added to spending.
- Payments-due view = Σ `installment_payments.amount_minor` by `due_month`.
- Deleting a transaction soft-deletes it, detaches observations (status back to CONFIRMED-unlinked → shown as "orphan" for re-link) and deletes reminders. Products linked to it keep existing (transaction_id set NULL) unless the user chooses to delete them too.
- `merge` and `unmerge` are transactional and logged in `match_decisions`.

---

## 7. Transaction Matching Engine

### 7.1 Overview

Runs whenever an observation is confirmed (or, for bank rows, when the review list is built so suggestions can be shown before confirmation).

```
new observation
  ├─ Step 1: exact duplicate?          → status=DUPLICATE (user notified, can override)
  ├─ Step 2: installment marker (k/n)? → installment matcher (Section 8)
  ├─ Step 3: candidate generation      → same user, |Δdate| ≤ 3 days, |Δamount| ≤ 2%,
  │                                      no CONFIRMED observation of the same source
  ├─ Step 4: scoring (7.3)
  └─ Step 5: decision (7.4)            → AUTO_ACCEPTED / PENDING suggestion / new transaction
```

### 7.2 Exact duplicates (same source)

`fingerprint = sha256(source | merchant_normalized | amount_minor | obs_date | obs_time or "" | installment_seq or "")`. For QR observations use `external_id` (ETTN). If an identical fingerprint exists for the user → `DUPLICATE`. Covers re-uploads and overlapping bank screenshots.

### 7.3 Scoring (deterministic baseline)

| Feature | Max | Function |
|---|---|---|
| Amount | 50 | 50 if equal; linear to 0 at 2% relative difference |
| Date | 20 | same day 20 · ±1 day 12 · ±2–3 days 5 |
| Merchant | 20 | 20 × similarity (alias hit = 1.0, else token_set_ratio/100) |
| Time | 10 | both known: 10 if |Δ| ≤ 5 min, linear to 0 at 60 min |

If a feature is unavailable (e.g. no time on the bank row), the score is renormalised: `score = earned / available_max × 100`. All feature values are stored in `match_decisions.features_json` (used later for the ML comparison in Section 19).

### 7.4 Decision thresholds (configurable, tuned in evaluation)

- `score ≥ 95` and exactly one candidate → **AUTO_ACCEPTED** merge, toast with **Undo**.
- `70 ≤ score < 95`, or multiple candidates ≥ 70 → **PENDING** suggestion: "Bu işlem daha önce eklediğin Migros fişiyle aynı olabilir. Birleştirilsin mi?"
- `< 70` → new transaction.

### 7.5 Merge semantics

Merging attaches the new observation to the existing transaction. Field precedence for the canonical record: QR > receipt > bank > manual for merchant display/date/time; total from QR/receipt when present (bank amount kept as evidence). Unmerge restores the previous state (observation becomes its own transaction) and sets the decision to `UNDONE`.

---

## 8. Installments (1:N Matching)

**Principle:** an installment purchase is **one spending** and **N payments**.

### 8.1 Creating a plan

A plan is created when any of these is true:
- receipt/POS slip extraction has `installment_count > 1`;
- a bank row carries a total amount with an installment label (e.g. "6 taksit");
- a bank row carries a `k/n` marker and no matching plan exists (plan inferred from the bank row);
- the user sets "Taksitli" on a transaction (manual).

Plan fields: `count = n`, `installment_minor = round(total/n)` with the last payment absorbing the rounding difference, `first_due_month` = purchase month + 1 by default (editable — banks differ), `total_payable_minor` = total unless the user enters a higher amount (financing cost = `total_payable − total`).

### 8.2 Matching a bank row with marker `k/n`

1. Candidates: plans of the same user, merchant similarity ≥ 0.8, `count = n`, `|installment_minor − amount| ≤ max(1 TRY, 1%)`, and the expected due month of payment `k` within ±1 month of the row date.
2. Best candidate found → payment `k` becomes `OBSERVED` and is linked to the observation (no new spending). Payments `< k` still `EXPECTED` become `INFERRED`.
3. No candidate → create an **estimated** purchase: `total = n × amount`, `purchase_date ≈ row_date − (k−1) months` (`is_estimated = true`), a plan, payments `< k` INFERRED, `k` OBSERVED, `> k` EXPECTED. When a receipt arrives later it is matched to this purchase by the normal 1:1 engine (amount = total) and the estimated fields are corrected.

### 8.3 Bank row without marker

If the amount ≈ `total/n` (n ∈ 2..12) of an existing purchase of the same merchant within 0–13 months → **suggest only**: "Bu ödeme MediaMarkt alışverişinin 6 taksitinden biri olabilir mi?" Never automatic.

### 8.4 Views

- **Spending view:** the full total in the purchase month.
- **Payments view:** each installment in its `due_month`; "Önümüzdeki aylar" mini chart (next 6 months); "Ocak'ta 3 taksitin bitiyor".
- Plan status becomes `COMPLETED` after the last due month; user can mark `CANCELLED`.

---

## 9. Refunds

- A refund is a `transactions` row with `kind=REFUND`, `refund_of_id` → original, `total_minor` ≤ original remaining amount (partial allowed).
- Created by: user action "İade edildi" on a purchase/product, or a bank `CREDIT` row matched to a purchase (same merchant, amount ≤ original, within 60 days) → suggestion.
- Effects: spending is reduced in the **original purchase's month** (the spending view shows net purchases, not cash movements). Linked product → `status=RETURNED`, return window `RETURNED`, reminders deleted.
- Cancelled installment plans after refunds: user marks the plan `CANCELLED` manually (automatic detection is out of scope).

---

## 10. Products, Warranties, Returns

### 10.1 When does a purchase become a product?

Suggested (never automatic) when a transaction or a receipt item has amount ≥ **1,000 TRY** (configurable) **and** category ∈ {TECHNOLOGY, HOME, CLOTHING}, or the merchant is an electronics/appliance retailer. The user can also create a product from any transaction or manually.

### 10.2 Defaults (always shown as suggestions with their source)

| Field | Default | Source label |
|---|---|---|
| Warranty end | purchase_date + 2 years (statutory minimum warranty for new goods, Law No. 6502 art. 56) | `LEGAL_DEFAULT` |
| Return window (ONLINE) | purchase_date + 14 days (right of withdrawal for distance sales, Law No. 6502 art. 48; legally counted from delivery — user can adjust) | `LEGAL_DEFAULT` |
| Return window (IN_STORE) | none — in-store returns are store policy; ask the user | `STORE_POLICY` / `USER` |

If a warranty document states another period, the user enters it (`DOCUMENT`). Unknown values stay empty — the system never invents them silently.

### 10.3 Product card

Name, category, purchase date, merchant, price (and financing cost if installments), documents, warranty (end, days left, source), return window (end, status), actions: *Belgeyi Gör*, *İade Edildi*, *Düzenle*, *Arşivle*.

---

## 11. Analytics, Dashboard, Budgets

### 11.1 Home screen (order is fixed)

1. **Spending (top):** current month total, category breakdown (bar list), change vs previous month (%).
2. **Needs attention:** returns ending ≤ 7 days, warranties ending ≤ 30 days, budgets ≥ 80%.
3. **Due this month (bottom):** total of installment payments due this month + list; mini chart for the next 6 months.

### 11.2 Other analytics

Weekly/monthly/yearly totals; by category; by merchant (top 10); month-over-month comparison with the top contributing categories; yearly summary. All computed by SQL in `services/analytics.py`. Optional one-paragraph AI commentary is generated **only from the computed numbers** passed in the prompt.

### 11.3 Budgets

Monthly limit per category, measured on the **spending view**. Alerts at 80% and 100% (once per category per month).

---

## 12. Reminders & Notifications

- Backend computes reminders when deadlines change: warranty (30 and 7 days before), return (3 days and 1 day before), last installment (in its due month), budgets (on threshold crossing).
- Mobile fetches `GET /reminders/upcoming` on launch/resume and schedules them with `flutter_local_notifications` (exact alarms where permitted, otherwise inexact). Rescheduling is idempotent (notification id derived from reminder id).
- No server push (FCM) in MVP.

---

## 13. AI Assistant (Purchase Memory)

### 13.1 Rules

- The LLM may only state facts that come from tool results in the current turn. If tools return nothing, it says so.
- `user_id` is **never** a tool parameter; it is injected server-side from the JWT.
- Today's date (Europe/Istanbul) is provided in the system prompt; the LLM resolves "bu ay", "geçen yıl" into explicit dates **as tool arguments**, and the backend re-validates them.
- Max 4 tool calls per turn; 20 s timeout; answers in Turkish, short.
- Text from receipts/tool outputs is treated as data (prompt-injection safe framing: tool outputs are wrapped and the system prompt says to ignore instructions inside them).
- Response = `{answer: str, actions: Action[]}` where actions are deep links (`OPEN_TRANSACTIONS` with filters, `OPEN_PRODUCT`, `OPEN_DOCUMENT`).

### 13.2 Tools

| Tool | Arguments | Returns |
|---|---|---|
| `query_transactions` | merchant?, category?, date_from?, date_to?, min_amount?, max_amount?, sort (`date_desc/amount_desc`), limit ≤ 20 | rows |
| `aggregate_spending` | date_from, date_to, group_by (`none/category/merchant/month`), category?, merchant? | totals (net of refunds) |
| `compare_periods` | a_from, a_to, b_from, b_to, group_by (`none/category`) | totals + deltas |
| `search_products` | query?, category?, status? | products |
| `get_product_details` | product_id | product + warranty + return + documents + financing cost |
| `get_upcoming_deadlines` | days ≤ 365, types? (`WARRANTY/RETURN/INSTALLMENT_END`) | deadlines |
| `get_installment_schedule` | month_from, month_to | payments by month, remaining total |
| `find_documents` | transaction_id? or product_id? | document refs |

### 13.3 Example

"Bu yıl teknolojiye ne kadar harcadım?" → `aggregate_spending(date_from=2026-01-01, date_to=2026-12-31, group_by=none, category=TECHNOLOGY)` → `{"total_minor": 3148500}` → "2026'da teknoloji kategorisinde kayıtlı harcamaların toplamı 31.485 TL." + action `OPEN_TRANSACTIONS{category: TECHNOLOGY, year: 2026}`.

---

## 14. AI Provider Layer

```python
class AIProvider(Protocol):
    def extract_receipt(self, masked_text: str, hints: ExtractionHints) -> ReceiptExtraction: ...
    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[BankRowExtraction]: ...
    def classify_category(self, merchant: str, items: list[str]) -> CategoryKey: ...
    def run_assistant(self, messages: list[Message], tools: list[ToolSpec], executor: ToolExecutor) -> AssistantResult: ...
```

- Implementations: `GeminiProvider` (default; model names from env `AI_MODEL_EXTRACT`, `AI_MODEL_ASSISTANT`), `FakeProvider` (deterministic fixtures for tests/CI). Optional later: `OllamaProvider` for local evaluation.
- All prompts live in `backend/app/ai/prompts/` as versioned markdown files (`receipt_extract.v1.md`, …); the prompt version is stored with each extraction.
- Retries: 1 retry on schema-invalid output, exponential back-off on 429; on failure return `EXTRACTION_FAILED` and let the user enter data manually.
- Every call logs: provider, model, prompt version, latency, token counts — **never** the text content.
- **Free-tier caveat:** free-tier providers may use submitted content to improve their products. Mitigations: mandatory on-device masking; development with the owner's own and synthetic data; documented as a limitation; production requires a paid tier or a local model (swap via `AIProvider`).

---

## 15. Privacy & Security

### 15.1 On-device PII masking (Dart, `mobile/lib/core/privacy/pii_masker.dart`)

Masks before upload, replacing with tokens like `[IBAN]`, `[CARD]`, `[TCKN]`, `[PHONE]`, `[EMAIL]`, `[BALANCE]`, `[NAME]`:

- IBAN: `TR\d{2}[ \d]{20,30}`.
- Card numbers: 13–19 digit sequences (with spaces/dashes) passing Luhn; partially masked forms like `4543 **** **** 1234`.
- TCKN: 11 digits passing the TCKN checksum.
- Phone numbers (+90 / 05xx patterns), e-mail addresses.
- Balance/limit lines: lines containing `Bakiye`, `Kullanılabilir`, `Limit`, `Toplam Borç`, `Hesap No` → whole line replaced.
- Names: lines following `Sayın`, `Ad Soyad`, `Kart Sahibi`, `Müşteri` → masked (heuristic, documented limitation).
- Unit tests with ≥ 40 synthetic cases; masking recall measured in evaluation (E4).

### 15.2 Backend security

- Passwords: Argon2id. JWT access 15 min; refresh 30 days, **rotating**, stored hashed, revocable; reuse detection revokes the family.
- Every repository method takes `user_id` and filters by it; integration tests assert cross-user access returns 404.
- Documents stored under `STORAGE_ROOT/users/<user_id>/<uuid>`; served only through `GET /documents/{id}/content?token=…` with a signed, 5-minute, single-document token.
- Rate limiting (simple in-process per-user limiter) on `/extract/*` and `/assistant/*`.
- Input limits: masked text ≤ 20 KB, uploads ≤ 10 MB, MIME whitelist (jpeg, png, pdf).
- Logs never contain OCR text, amounts with merchant names together, tokens or e-mails.
- Account deletion: `DELETE /me` removes all rows and files.

### 15.3 Data retention & consent

- First-run consent screen (Turkish) explains: on-device OCR, masking, that masked text is processed by an external AI provider, what is stored, and how to delete. Must accept to use AI extraction (otherwise manual entry only).
- Settings toggle: "Fiş görsellerini sakla" (default ON — needed as warranty proof). Bank screenshots are never stored.
- Real personal data never goes into the repository; `ai/datasets/` is git-ignored.

---

## 16. API Overview

All endpoints under `/api/v1`, JSON, JWT bearer auth except auth endpoints. Errors: `{ "error": { "code": "STRING_CODE", "message": "..." } }`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /me` · `DELETE /me` |
| Reference | `GET /categories` |
| Extraction | `POST /extract/receipt` · `POST /extract/einvoice-qr` · `POST /extract/bank-screenshot` |
| Observations | `GET /observations?status=PENDING_REVIEW` · `POST /observations/{id}/confirm` (body: edited fields, create_product?) · `POST /observations/{id}/reject` |
| Matching | `GET /matches?decision=PENDING` · `POST /matches/{id}/accept` · `POST /matches/{id}/reject` · `POST /transactions/{id}/unmerge` |
| Transactions | `GET /transactions` (filters, pagination) · `POST /transactions` (manual) · `GET/PATCH/DELETE /transactions/{id}` · `POST /transactions/{id}/refund` |
| Installments | `GET /installments/schedule?from=&to=` · `PUT /transactions/{id}/installment-plan` · `PATCH /installment-plans/{id}` |
| Documents | `POST /documents` (multipart) · `GET /documents/{id}` · `POST /documents/{id}/access-token` · `GET /documents/{id}/content?token=` · `DELETE /documents/{id}` |
| Products | `GET/POST /products` · `GET/PATCH/DELETE /products/{id}` · `PUT /products/{id}/warranty` · `PUT /products/{id}/return-window` · `GET /products/suggestions` |
| Analytics | `GET /analytics/home?month=` · `GET /analytics/spending?from=&to=&group_by=` · `GET /analytics/compare?...` · `GET /analytics/year?year=` |
| Budgets | `GET/PUT /budgets` · `DELETE /budgets/{category_key}` |
| Reminders | `GET /reminders/upcoming` · `POST /reminders/{id}/dismiss` |
| Assistant | `POST /assistant/chat` · `DELETE /assistant/history` |

The OpenAPI schema generated by FastAPI is the contract; mobile models are written against it.

---

## 17. Mobile App Structure & Screens

```
mobile/lib/
├── main.dart, app.dart (router, theme)
├── core/      networking/ (Dio, auth interceptor) · storage/ (secure storage) · privacy/ (PII masker)
│              ocr/ (ML Kit wrappers, QR) · theme/ (design tokens) · utils/ (money, dates, tr locale)
└── features/  auth/ · home/ · capture/ · receipt_review/ · bank_import/ · matches/
               transactions/ · installments/ · products/ · budgets/ · assistant/ · settings/
```

Each feature: `data/` (API + DTOs), `domain/` (models), `presentation/` (screens, widgets, Riverpod providers).

**Bottom navigation:** Ana Sayfa · Harcamalar · **(+)** · Ürünler · Asistan. The (+) sheet: Fiş Tara · Galeriden Ekle · Banka Ekran Görüntüsü · Manuel Harcama · Ürün Ekle.

**Screens:** Splash · Consent · Login · Register · Home · Transactions list (filters) · Transaction detail (evidence list, merge/unmerge, refund, installments) · Capture (camera) · Receipt review · Bank import review (row list with match badges) · Match suggestion sheet · Installments (schedule) · Products list (tab "Teknoloji Kasam") · Product detail · Product edit · Document viewer · Budgets · Assistant chat · Settings (privacy toggles, delete account, logout).

UI copy is Turkish; money formatted `1.349,90 TL`; dates `09 Kasım 2026`. Visual design comes from the design track (`docs/design/DESIGN_TRACK.md`); until then use the placeholder tokens in `core/theme/`.

---

## 18. Tech Stack

| Layer | Choice |
|---|---|
| Mobile | Flutter (stable), Dart 3, Android only (minSdk 24) |
| State / routing / HTTP | Riverpod (with code generation), go_router, Dio |
| On-device ML | `google_mlkit_text_recognition`, `google_mlkit_barcode_scanning` |
| Capture & share | `camera` / `image_picker`, `receive_sharing_intent`, `pdfx` (PDF → image) |
| Mobile storage | `flutter_secure_storage` (tokens), `shared_preferences` (settings) |
| Notifications | `flutter_local_notifications` (+ `timezone`) |
| Charts | `fl_chart` |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic |
| Matching utils | rapidfuzz |
| Auth | argon2-cffi, PyJWT |
| AI | `google-genai` SDK behind `AIProvider` |
| DB | PostgreSQL 16 (Docker) |
| Storage | Local filesystem behind `StorageBackend` interface |
| Tooling | uv (Python deps), ruff (lint+format), pytest + pytest-asyncio + httpx, flutter_lints, flutter_test |
| Dev infra | Docker Compose (postgres + backend) |
| CI | GitHub Actions: backend lint+tests, flutter analyze+tests |
| Experiments | Python notebooks/scripts in `ai/experiments/`, pandas, scikit-learn, matplotlib |

---

## 19. Research & Evaluation Plan

**Research question:** *How accurately can purchase information be extracted from heterogeneous Turkish financial and commercial documents on a privacy-preserving mobile pipeline, and how reliably can records from different sources (receipts, e-invoices, bank screenshots) be reconciled, including installment purchases?*

### E1 — Extraction

- Dataset: 150–300 of the owner's receipts (photographed with the app's capture flow), labelled with gold JSON via a small labelling script; subset of e-Archive invoices with QR. Split by merchant (no merchant in both dev and test).
- Systems: **S1** OCR + regex rules · **S2** OCR + LLM · **S3** OCR + LLM + validation (ours) · **S4** QR-first hybrid + S3 (ours, full) · **S5** image → multimodal LLM directly (privacy-unfriendly baseline).
- Metrics: field exact-match for merchant (normalised), date, total; item-level precision/recall/F1 (fuzzy name ≥ 85 + exact price); category accuracy; latency; tokens; for S5 note that unmasked images are sent.

### E2 — Matching

- Dataset: pairs built from the owner's receipts + bank screenshots for the same period, plus synthetic bank rows; gold labels: same purchase / installment k of plan / unrelated.
- Systems: deterministic scorer (7.3) vs logistic regression on the same features (5-fold CV).
- Metrics: precision, recall, F1, PR curve; threshold selection; separate results for 1:1 and 1:N.

### E3 — Assistant

- 60–100 Turkish questions over a seeded demo database with gold answers computed by SQL; include unanswerable questions.
- Metrics: tool-selection accuracy, numeric answer correctness, hallucination rate (numbers in answers not present in tool outputs), correct "no data" responses, latency.

### E4 — Privacy

- Synthetic screenshots/texts with injected PII; masking recall and false-positive rate.

**All reported numbers come from real runs.** No placeholder results in the report.

---

## 20. Testing Strategy

- **Backend unit:** normaliser, validation engine, scorer, installment matcher, QR parser, date resolver, analytics queries.
- **Backend integration (pytest + test Postgres):** each router; **cross-user isolation** for every resource; assistant tools cannot return other users' data.
- **Mobile unit:** PII masker, money/date formatting, QR detection mapping.
- **Mobile widget tests:** review screens, home screen.
- **Golden fixtures:** `backend/tests/fixtures/` contains masked OCR texts and expected extractions; `FakeProvider` replays them.
- **CI must be green before a phase is marked done.**

---

## 21. Repository Layout

```
receiptbox-ai/
├── CLAUDE.md
├── .claude/skills/receiptbox-scope/SKILL.md
├── mobile/                 # Flutter app
├── backend/
│   ├── app/{api,services,repositories,models,schemas,ai,matching,qr,reminders,security,storage,core}
│   ├── migrations/         # Alembic
│   ├── tests/
│   └── pyproject.toml
├── ai/
│   ├── experiments/        # E1–E4 scripts/notebooks
│   └── datasets/           # git-ignored
├── infra/docker-compose.yml
└── docs/
    ├── spec/00_PROJECT_SPEC.md
    ├── phases/             # P00 … P16
    ├── design/DESIGN_TRACK.md
    ├── DECISIONS.md
    └── PROGRESS.md
```

---

## 22. Implementation Phases (summary)

| Phase | Title | Week |
|---|---|---|
| P00 | Repository bootstrap & tooling | 1 |
| P01 | Backend data model & migrations | 1 |
| P02 | Backend authentication | 2 |
| P03 | Mobile app shell & auth | 2 |
| P04 | On-device capture: OCR, QR, PII masking, share | 3 |
| P05 | AI provider layer & receipt extraction | 4 |
| P06 | e-Invoice QR, merchant normalisation, categorisation | 5 |
| P07 | Receipt review flow, manual entry, documents | 5–6 |
| P08 | Bank screenshot import | 7 |
| P09 | Matching engine 1:1 | 8 |
| P10 | Installments 1:N | 9 |
| P11 | Dashboard, analytics, budgets | 10 |
| P12 | Products, warranties, returns, refunds | 11 |
| P13 | Reminders & local notifications | 11 |
| P14 | AI assistant | 12 |
| P15 | Evaluation harness & experiments | 13 |
| P16 | Hardening, security tests, demo | 14 |

Parallel tracks: **Design** (screens in Figma/Claude, weeks 1–4) and **Data labelling** (weeks 2–12). Details: `docs/phases/README.md`.

---

## 23. Glossary

| Term | Meaning |
|---|---|
| Observation | One piece of evidence about a purchase from one source (receipt, QR, bank row, manual). Immutable after confirmation. |
| Transaction | The canonical purchase (or refund) that observations are attached to. |
| Merge / Unmerge | Attaching an observation to an existing transaction / reverting that. |
| Installment plan | The N-payment schedule of a single purchase. |
| Spending view | Purchases counted fully in their purchase month. |
| Payments view | Installment payments counted in their due month. |
| GİB QR | QR code on Turkish e-Archive / e-Invoice documents containing structured invoice data. |
| ETTN | Universal unique ID of a Turkish e-document; used as `external_id`. |
| PII masking | Replacing personal/financial identifiers on the device before upload. |
