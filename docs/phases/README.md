# Implementation Phases

17 phases, each small enough for one focused Claude Code session series (≈ 2–4 working days). **Strictly sequential.** Each phase file has the same structure: Goal · Depends on · Read first · Scope · Out of scope · Deliverables · Acceptance criteria · Tests · Manual check for the owner.

| Phase | File | Week | Main output |
|---|---|---|---|
| P00 | [P00_bootstrap.md](P00_bootstrap.md) | 1 | Monorepo, Docker, CI, skeleton apps |
| P01 | [P01_data_model.md](P01_data_model.md) | 1 | All tables + migrations + seeds |
| P02 | [P02_auth.md](P02_auth.md) | 2 | Register/login/refresh/logout/delete |
| P03 | [P03_mobile_shell.md](P03_mobile_shell.md) | 2 | Flutter shell, navigation, auth screens |
| P04 | [P04_capture_ocr_privacy.md](P04_capture_ocr_privacy.md) | 3 | Camera/gallery/share, OCR, QR, PII masker |
| P05 | [P05_ai_receipt_extraction.md](P05_ai_receipt_extraction.md) | 4 | AIProvider, receipt extraction, validation, confidence |
| P06 | [P06_qr_merchants_categories.md](P06_qr_merchants_categories.md) | 5 | GİB QR parser, merchant normaliser, categoriser |
| P07 | [P07_receipt_review_documents.md](P07_receipt_review_documents.md) | 5–6 | End-to-end receipt → transaction, manual entry, documents |
| P08 | [P08_bank_screenshots.md](P08_bank_screenshots.md) | 7 | Bank screenshot extraction & review |
| P09 | [P09_matching_1to1.md](P09_matching_1to1.md) | 8 | Duplicate detection, scorer, merge/unmerge |
| P10 | [P10_installments.md](P10_installments.md) | 9 | Installment plans & 1:N matching |
| P11 | [P11_dashboard_budgets.md](P11_dashboard_budgets.md) | 10 | Home screen, analytics, budgets |
| P12 | [P12_products_warranty_refunds.md](P12_products_warranty_refunds.md) | 11 | Products, warranty, returns, refunds |
| P13 | [P13_reminders.md](P13_reminders.md) | 11 | Reminder computation, local notifications |
| P14 | [P14_ai_assistant.md](P14_ai_assistant.md) | 12 | Tool-calling assistant + chat UI |
| P15 | [P15_evaluation.md](P15_evaluation.md) | 13 | E1–E4 experiments, result tables |
| P16 | [P16_hardening_demo.md](P16_hardening_demo.md) | 14 | Security tests, demo data, release APK |

## Parallel tracks (owner)

- **Design:** weeks 1–4, see `docs/design/DESIGN_TRACK.md`.
- **Data:** from week 2, photograph receipts with the app (after P04) and keep a labelled set for E1; collect masked bank screenshots for P08 and E2.

## Milestones

- **M1 (end of week 6):** receipt → reviewed transaction works on a phone.
- **M2 (end of week 9):** bank screenshots + matching + installments work. *Core thesis contribution done.*
- **M3 (end of week 12):** full MVP incl. assistant.
- **M4 (end of week 14):** evaluation results + demo-ready APK.

If behind schedule: cut in this order → P13 budget notifications, P11 yearly view, assistant tools `compare_periods`/`find_documents`. Never cut P09, P10, P15.

## How to start a phase in Claude Code

```
Load the receiptbox-scope skill. Read docs/PROGRESS.md and docs/phases/P0X_*.md.
Give me a plan first, then implement P0X only.
```
