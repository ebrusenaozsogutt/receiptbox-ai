# Decisions Log

Format: `D-NNN · date · decision · reason`. Only the owner moves items from "Open" or "Proposed" to "Accepted".

## Accepted

| ID | Date | Decision | Reason |
|---|---|---|---|
| D-001 | 2026-11-15 | Single-semester project, scope per spec §3 | Instructor approval for one semester |
| D-002 | 2026-11-15 | Android only (Flutter); no iOS | Owner uses Windows; reduces effort |
| D-003 | 2026-11-15 | Free LLM tier (Gemini) behind `AIProvider`; mandatory on-device masking | No budget; privacy mitigation |
| D-004 | 2026-11-15 | Target users 18+, general adult population; UI Turkish; no parental consent flow | Owner decision |
| D-005 | 2026-11-15 | Home order: spending (top) → needs attention → due this month (bottom); budgets on spending view | Owner decision |
| D-006 | 2026-11-15 | Manual cash purchases and basic (full/partial) refunds in MVP; installment cancellation manual; TRY only | Cheap, prevents data gaps |
| D-007 | 2026-11-15 | Observations (evidence) vs transactions (canonical) model; reversible merges | Needed for 1:1 and 1:N matching and research logging |
| D-008 | 2026-11-15 | No Redis/Celery/FCM/offline sync/RAG in MVP | Single-semester scope |
| D-009 | 2026-11-15 | Money stored as BIGINT minor units | Avoid float errors |
| D-010 | 2026-11-15 | Claude Code writes the code; owner reviews/tests each phase | Owner decision |
| D-011 | 2026-11-15 | All md docs in English | Owner decision |
| D-012 | 2026-11-16 | Money columns are `BIGINT NOT NULL CHECK (>= 0)` except four where the amount can be genuinely unknown: `observations.amount_minor`, `receipt_items.unit_price_minor`, `receipt_items.total_price_minor`, `products.purchase_price_minor` (NULL allowed, never 0 as a placeholder) | Owner chose this in the P01 plan; avoids silently inventing amounts (invariant 7) |

## Open (need owner input)

| ID | Question | Needed by |
|---|---|---|
| O-001 | Which 2–3 banks to support? Owner will provide masked screenshots (list view, an installment row, detail view). | P08 |
| O-002 | Final visual design (colors, typography, key screens) — design track with Figma/Claude. | P03 (placeholder tokens until then) |
| O-003 | Sample receipts incl. an e-Archive invoice with QR and a POS slip with installments. | P05 |

## Proposed / not approved

_(Claude Code: write feature ideas here instead of implementing them.)_

Implementation choices made in P00 that the owner may want to confirm (none adds scope):

| ID | Date | Choice | Reason |
|---|---|---|---|
| P-001 | 2026-11-15 | Docker database is published on host port **5433**, not 5432 | A PostgreSQL 17 Windows service already uses 5432 on the owner's PC; also stops tests from touching it by accident |
| P-002 | 2026-11-15 | Generated `*.g.dart` (Riverpod) are git-ignored; CI and README run `build_runner` | Keeps diffs small; spec §18 asks for Riverpod code generation |
| P-003 | 2026-11-15 | Mobile uses `package:material_ui` instead of `package:flutter/material.dart` | Flutter 3.50 deprecates the old import; `flutter create` already generates the new one |
| P-004 | 2026-11-15 | `AI_MODEL_EXTRACT`/`AI_MODEL_ASSISTANT` are empty until P05 | Model names must come from env vars (CLAUDE.md); no guessing of model IDs |
| P-005 | 2026-11-15 | Compose backend reads a committed, clearly fake `infra/dev-defaults.env`, then the optional repo-root `.env` | `up -d` works before a `.env` exists; real values override it |
| P-006 | 2026-11-15 | uvicorn's own access log is disabled; the app logs method/path/status/duration itself | uvicorn would print query strings, which will later carry document tokens |
| P-007 | 2026-11-16 | Enums are `VARCHAR + CHECK` (not native PostgreSQL enums) everywhere | Adding a value to a native enum is awkward in Alembic; the phase file asked for one consistent choice |
| P-008 | 2026-11-16 | `observations.direction` values are `DEBIT` / `CREDIT`; amounts are always >= 0 | Spec 6.1 names the column but not its values |
| P-009 | 2026-11-16 | `transactions.merchant_id` and `category_id` are nullable; `observations.fingerprint` is NOT NULL; `warranties.start_date` is nullable, `end_date` NOT NULL; `match_decisions.score` is nullable `NUMERIC(6,2)` | Spec 6.1 lists the columns without nullability; unknown values stay empty (invariant 7) |
| P-010 | 2026-11-16 | Database-level partial unique index `uq_observations_one_confirmed_per_source` enforces spec 6.3 (one CONFIRMED observation per source per transaction, bank rows linked through installment payments excepted) | A database guard is safer than relying on service code alone; P09 must respect it when merging |
| P-011 | 2026-11-16 | `receipt_items`, `installment_plans`, `installment_payments`, `warranties`, `return_windows` have no `user_id` (as in spec 6.1); they are reached through their parent, which does. `reminders.target_id` is not a foreign key because it points at different tables by `type` | Follows the spec literally; later repositories must join through the parent |
| P-012 | 2026-11-16 | `merchants_seed.csv` (223 merchants, 691 aliases) was authored by Claude from general knowledge; every alias also has an ASCII-folded variant (POS slips often drop Turkish letters) | Needed >= 150 merchants; owner should review names and default categories |
| P-013 | 2026-11-16 | Money parser reads a lone separator followed by exactly three digits as thousands (`1.349` = 1349 TL) and rejects `1,349` as ambiguous; negatives are rejected | Turkish lira has two decimals, so three digits cannot be decimals; ambiguity is rejected rather than guessed |
| P-014 | 2026-11-16 | All database URLs use `127.0.0.1` instead of `localhost` | On the owner's Windows PC `localhost` adds ~2 s to every connection (IPv6 attempt first) |
| P-015 | 2026-11-16 | A refresh-token "family" is the chain of rows linked by `replaced_by`; reuse detection walks it with a recursive query. No `family_id` column | Spec 6.1 lists no such column; avoids a schema change. A `family_id` column would be simpler and faster if the chain ever gets long |
| P-016 | 2026-11-16 | Registering an existing e-mail returns 409 `EMAIL_ALREADY_REGISTERED` | Without e-mail verification there is no way to hide whether an address is registered; login still gives one identical answer for "wrong password" and "unknown e-mail" |
| P-017 | 2026-11-16 | E-mail format is checked with an ASCII-only regex (no `email-validator` dependency); passwords are 8-128 characters with at least one letter and one digit | Python's and PostgreSQL's `lower()` can disagree on some non-ASCII letters and would trip the lowercase CHECK; fewer dependencies |
| P-018 | 2026-11-16 | `JWT_SECRET` shorter than 32 characters stops the server at start-up | HS256 needs a 256-bit key; fails loudly instead of running with a weak secret |
| P-019 | 2026-11-16 | Parallel refreshes with the same token: the second counts as reuse and revokes the family; the mobile app must serialise refreshes (P03) | Keeps reuse detection strict; a grace window would weaken it |
| P-020 | 2026-11-16 | `POST /auth/logout` needs no access token, always answers 204, and does not revoke access tokens already issued (they expire within 15 minutes) | Idempotent and leaks nothing; server-side access-token revocation would need a denylist |
| P-021 | 2026-11-16 | Login rate limit counts every attempt (also successful ones), per e-mail + client IP seen by the app, in-process | Matches "5/min per email+IP" in the phase file; per-process state is enough for one server |
| P-022 | 2026-11-16 | `DELETE /me` removes the database rows first, then the files; a file-removal failure is logged (error type only) and does not fail the request | The account must not survive because of a disk error; orphaned files are a known gap to revisit in P16 |
| P-024 | 2026-11-16 | New mobile dependencies: `flutter_secure_storage` (tokens in the Android Keystore) and `shared_preferences` (settings), both in spec 18; `flutter_svg` (draws the Figma SVG icons of the bottom bar); `integration_test` (dev, emulator test) | One-line reasons; `flutter_svg` and `integration_test` are not named in spec 18 |
| P-025 | 2026-11-16 | Plus Jakarta Sans is **bundled** (`assets/fonts/PlusJakartaSans-Variable.ttf`, SIL OFL licence in `assets/fonts/OFL.txt`, shown on the app's licences page) instead of loading it from Google at run time; the 5 bottom-bar icons are the Figma SVGs in `assets/icons/` | No network call to Google (privacy), works offline |
| P-026 | 2026-11-16 | The consent screen has two buttons: "Kabul ediyorum" (`ai_consent = true`) and "Şimdilik kabul etmiyorum" (`false`: AI extraction off, manual entry only, spec 15.3). P03 only stores the value; later phases must check it. Settings has no AI toggle yet (the phase lists only "Fiş görsellerini sakla") | Spec 15.3 says AI extraction needs consent, manual entry does not |
| P-027 | 2026-11-16 | A local flag `has_account` decides where a signed-out user lands: Login if this device has had an account, Register on a fresh install and after the account was deleted | "Delete account returns to Register", "logout returns to Login" |
| P-028 | 2026-11-16 | The refresh interceptor never refreshes twice with the same token (a request that fails late with an old token just retries), and a refresh that fails because of the network keeps the session and reports the network error | Refresh tokens are single-use (P-019); a bad network must not sign anyone out |
| P-029 | 2026-11-16 | Colors, font sizes, spacing, radii and component sizes exist only in `core/theme/`; `test/theme_tokens_guard_test.dart` fails if a hard-coded value appears elsewhere. Login/Register/Consent have no Figma frames yet (see DESIGN_TRACK row 8). `features/shell/` holds the bottom bar and (+) sheet (not in the spec 17 list) | The owner wants to change the design in one place; spec 17 lists feature folders as examples |
| P-030 | 2026-11-16 | Bottom bar deviations from the static Figma frame: tabs are flexible (labels get an ellipsis instead of overflowing on narrow phones), system text scale is capped at 1.2 for the bar, the whole bar height is the tap area, the (+) sheet is scrollable | Found by tests: the bar overflowed on narrow screens / large fonts, the sheet overflowed on short screens |
| P-031 | 2026-11-16 | `android:allowBackup="false"` | Keystore-bound tokens cannot be restored from a backup; avoids a broken session after a restore |
| P-032 | 2026-11-16 | P00's "Sunucu: bağlı" screen became a status row in Settings. The emulator test (`integration_test/app_e2e_test.dart`) is not part of CI (no emulator there) | The placeholder screen is replaced by the real app shell |
| P-023 | 2026-11-16 | **Future work, not approved:** OAuth sign-in (Google/Apple), e-mail verification, password-reset e-mails | Listed as out of scope in the P02 phase file |
