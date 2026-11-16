# Progress

Update after every phase. Newest entry on top of the log.

## Status board

| Phase | Title | Status | Date done |
|---|---|---|---|
| P00 | Repository bootstrap & tooling | ✅ Done | 2026-11-16 |
| P01 | Backend data model & migrations | ✅ Done | 2026-11-16 |
| P02 | Backend authentication | ✅ Done | 2026-11-16 |
| P03 | Mobile app shell & auth | ✅ Done | 2026-11-16 |
| P04 | On-device capture: OCR, QR, PII masking, share | ⬜ | |
| P05 | AI provider layer & receipt extraction | ⬜ | |
| P06 | e-Invoice QR, merchant normalisation, categorisation | ⬜ | |
| P07 | Receipt review flow, manual entry, documents | ⬜ | |
| P08 | Bank screenshot import | ⬜ | |
| P09 | Matching engine 1:1 | ⬜ | |
| P10 | Installments 1:N | ⬜ | |
| P11 | Dashboard, analytics, budgets | ⬜ | |
| P12 | Products, warranties, returns, refunds | ⬜ | |
| P13 | Reminders & local notifications | ⬜ | |
| P14 | AI assistant | ⬜ | |
| P15 | Evaluation harness & experiments | ⬜ | |
| P16 | Hardening, security tests, demo | ⬜ | |

Legend: ⬜ not started · 🟨 in progress · ✅ done · ⛔ blocked

## Log

<!--
### YYYY-MM-DD — P0X <title>
- Done:
- Tests added:
- Manual test steps for the owner:
- Known gaps / follow-ups:
-->

### 2026-11-16 — P03 CI confirmed
- CI run on `main` (`96553ae`): jobs `backend` and `mobile` both green (the mobile job runs `build_runner`, `flutter analyze` and the 192 Flutter tests on GitHub's runner). P03 is closed.

### 2026-11-16 — P03 Mobile app shell & auth (done locally; CI confirmed later the same day)
- Done:
  - **Theme (`mobile/lib/core/theme/`)** from the Figma "Direction v1" tokens read with the Figma connector: colors, type scale (Plus Jakarta Sans, bundled with its OFL licence), spacing, radii 8/12/16/24, component sizes, shadows, one `ThemeData`. Nothing else in `lib/` may contain a color or size: `test/theme_tokens_guard_test.dart` fails if it does.
  - **Bottom navigation** built from the Figma component `BottomNav` (node 2:22): Ana Sayfa · Harcamalar · (+) · Ürünler · Asistan, 76 high, the (+) a raised 56×56 rounded square (radius 18, teal shadow); icons are the Figma SVGs. The (+) opens a sheet with Fiş Tara, Galeriden Ekle, Banka Ekran Görüntüsü, Manuel Harcama, Ürün Ekle (placeholder pages).
  - **Auth in the app:** Splash (token check + `/me`) → Consent (spec 15.3 text; two buttons) → Register (18+ checkbox required) / Login → main shell. Tokens in `flutter_secure_storage`, settings in `shared_preferences`.
  - **Dio auth interceptor:** adds the access token; on 401 refreshes once and retries; concurrent 401s share ONE refresh (refresh tokens are single-use, see P02); a late 401 from an old token just retries; refresh rejected → tokens deleted, back to Login with an explanation; refresh failing for network reasons keeps the session.
  - **Settings** (gear on Home): e-mail, "Fiş görsellerini sakla" (default ON, local), server status row (P00's "Sunucu: bağlı"), Çıkış yap, Hesabı sil (confirmation, then Register).
  - **Shared widgets:** `MoneyText` (`1.349,90 TL`), `DateText` (`09 Kasım 2026`), `EmptyState`, `ErrorView`, `LoadingView`, `MessageBanner`, `AppTextField`. Backend error codes → Turkish messages in one file (`core/networking/api_error.dart`).
  - Android: `allowBackup="false"`, app label "ReceiptBox AI".
- Tests added: **192 Flutter tests** (was 3): money/date formatting, error mapping, interceptor (12 cases with a scripted fake network), router redirect rules, form validators, login / register (18+) / consent screens, full app flows (fresh install, restart, revoked session, offline start, logout, delete account), main shell and the 5 (+) actions, bottom-nav measurements against Figma (76, 56×56, radius 18, shadow, label style, tap targets, no overflow on narrow screens / large fonts), settings, server status tile, theme tokens against the Figma values, and the guard test. Plus `integration_test/app_e2e_test.dart`.
- Verified on the **Android emulator against the real backend** (`flutter test integration_test/app_e2e_test.dart -d emulator-5554 ...`, passes): consent → register (18+ error first) → Home; 4 tabs and all 5 (+) actions; restart keeps the session; a garbage access token is renewed silently (refresh token rotated); a revoked refresh token → Login with the "Oturum süren doldu" message; wrong password message; login; settings; logout → Login; delete account → Register, and the account is really gone on the server. Screenshots of the consent, register, Home/Harcamalar screens match the Figma look.
- Checks run on 2026-11-16: `ruff check`, `ruff format --check`, `pytest` (285 passed), `flutter analyze` (no issues), `flutter test` (192 passed), the emulator test.
- Manual test steps for the owner: README §3.3 ("What you should see").
- Problems found by the tests and fixed in this phase: the bottom bar overflowed on narrow screens / large system fonts; the (+) sheet overflowed on short screens; the bar tabs gave screen readers no tap action; Dart's `toUpperCase()` turned "Gizlilik" into "GIZLILIK" (Turkish needs "GİZLİLİK"); a network failure during refresh would have signed the user out; the keyboard stayed open after submitting a form.
- Known gaps / follow-ups:
  - ~~CI for this phase has not run yet~~ → green on 2026-11-16, see the entry above.
  - Login / Register / Consent have no Figma frames; they were built from the tokens and components. Please design or review them (DESIGN_TRACK row 8).
  - Only 7 of 13 category colors exist in Figma so far.
  - The emulator test is not in CI (no emulator on GitHub's runners). Do not run an `adb` screenshot loop while it runs: that disturbed an earlier run.
  - On this PC Docker Desktop sometimes stops by itself; `docker desktop start` brings it back (backend tests need it).
  - The AI consent value is stored but nothing uses it yet (P05), and Settings has no toggle for it.
  - Tested on the emulator only, not on a real phone.

### 2026-11-16 — P02 CI confirmed
- CI run on `main` (`471dc5f`): jobs `backend` and `mobile` both green, including the 285 backend tests on a fresh PostgreSQL service with the longer test `JWT_SECRET`. P02 is closed.

### 2026-11-16 — P02 Backend authentication (done locally; CI confirmed later the same day)
- Done:
  - Endpoints under `/api/v1`: `POST /auth/register` (201), `/auth/login`, `/auth/refresh`, `/auth/logout` (204), `GET /me`, `DELETE /me` (204). Layers: `api/auth.py`, `api/deps.py` (`get_current_user`), `services/auth.py`, `repositories/users.py` + `refresh_tokens.py`, `schemas/auth.py`, `security/{passwords,tokens,rate_limit}.py`, `storage/files.py`.
  - Argon2id passwords (argon2-cffi defaults = RFC 9106 low-memory profile, hash upgraded on login if parameters change); access JWT (HS256, 15 min, `sub` = user id, `typ` = access, algorithm pinned); refresh token = 256 random bits, only its SHA-256 is stored, 30 days, **rotated on every use**; reuse of a revoked token revokes the whole family (found by walking the `replaced_by` chain, no schema change) and returns 401.
  - Error codes: `AUTH_INVALID_TOKEN`, `AUTH_EXPIRED`, `AUTH_INVALID_CREDENTIALS` (same answer for wrong password and unknown e-mail, with a dummy hash check so timing does not leak), `EMAIL_ALREADY_REGISTERED` (409), `INVALID_EMAIL` / `WEAK_PASSWORD` / `ADULT_CONFIRMATION_REQUIRED` (422), `RATE_LIMITED` (429 + `Retry-After`). 401s carry `WWW-Authenticate: Bearer`.
  - Argon2 hashing/verification runs in a worker thread (`asyncio.to_thread`), so a login does not freeze the single-process server for the ~50 ms it takes.
  - Login rate limit: 5 attempts per minute per e-mail + IP (in-process sliding window, injectable clock; e-mail is hashed in memory).
  - `DELETE /me`: user row (FK cascades remove every row they own) then `STORAGE_ROOT/users/<id>/`.
  - `JWT_SECRET` must be at least 32 characters (checked at start-up, the rejected value is never echoed); test and CI secrets were lengthened.
  - New dependencies: `argon2-cffi`, `PyJWT` (both in spec §18).
- Tests added (285 backend tests in total, 90 new): `tests/api/test_auth.py` (60: happy paths, wrong password, duplicate e-mail, weak password / bad e-mail / 18+, rotation, reuse and family revocation, expired refresh and access tokens, forged tokens incl. `alg: none`, parallel refresh, logout, rate limit per e-mail / per IP / sliding window, passwords and tokens never in logs or responses, OpenAPI), `tests/test_security.py` (passwords, tokens, settings check, limiter, storage cleanup), `tests/test_delete_account.py` (data in 16 tables for two users, only the deleted user's rows and files disappear, old credentials stop working, storage failure does not undo the deletion).
- Checks run on 2026-11-16: `ruff check`, `ruff format --check`, `pytest` (285 passed, also on a brand-new empty database), live smoke test of the whole Swagger flow against the rebuilt Docker backend (register → me → refresh x2 → reuse 401 → family dead → logout → delete → 401 → rate limit 429).
- Manual test steps for the owner: README §3.2.2 (Swagger UI at `http://localhost:8000/docs`).
- Known gaps / follow-ups:
  - ~~CI for this phase has not run yet~~ → green on 2026-11-16, see the entry above.
  - Two refreshes with the same token at the same moment cannot both succeed: the second is treated as reuse and the family is revoked. The mobile app (P03) must serialise refreshes.
  - Logout revokes the refresh token only; an already issued access token stays valid until it expires (max 15 minutes).
  - The rate limiter keys on the client IP the app sees (behind a reverse proxy that would be the proxy's IP) and resets when the server restarts.
  - If deleting the user's files fails after the database delete, only the error type is logged and the request still succeeds; orphaned files are possible (revisit in P16).
  - Not implemented, by design (see DECISIONS P-023): OAuth, e-mail verification, password reset e-mails.
  - `pytest`'s `tmp_path` does not work on this PC (the Windows user name has non-ASCII letters), so tests use their own `storage_root` fixture built on `tempfile`.

### 2026-11-16 — P01 CI confirmed
- CI run on `main` (`90c185b`): jobs `backend` and `mobile` both green, including the migration tests on a fresh PostgreSQL service. P01 is closed.

### 2026-11-16 — P01 Backend data model & migrations (done locally; CI confirmed later the same day)
- Done:
  - ORM models for all 19 tables of spec §6.1 (`backend/app/models/`), enums as `VARCHAR + CHECK`, UUID pk with `gen_random_uuid()`, `created_at`/`updated_at`, money as `BIGINT >= 0`, no float columns.
  - Alembic (async) + `0001_initial` (autogenerated, then reviewed by hand: column-level money CHECKs were missing from the autogenerated output and were added) + `0002_seed` (13 categories, 223 merchants, 691 global aliases from `backend/data/merchants_seed.csv`). Upgrade and downgrade both work.
  - DB rules: partial unique index for "one CONFIRMED observation per source" (spec §6.3), `UNIQUE NULLS NOT DISTINCT` on global aliases, first-of-month CHECKs for installments, lowercase e-mail CHECK, cascades for account deletion.
  - `UserScopedRepository[T]` (`app/repositories/base.py`): `user_id` is a required `uuid.UUID` on every method.
  - `app/core/money.py` (Turkish text ↔ kuruş) and `app/core/text.py` (Turkish uppercase + punctuation step of spec §5.6).
  - Dockerfile now ships `alembic.ini`, `migrations/` and `data/`; README explains migrations and DBeaver.
- Tests added (195 backend tests in total, 188 new): `test_money.py`, `test_models_schema.py` (also compares the migrated DB with the models and checks CHECK constraints in the catalog), `test_migrations.py` (down to base, back to head, seed on its own), `test_seed.py`, `test_constraints.py` (21 database-rule tests), `test_user_scoped_repository.py` (two users, cross-user access).
- Checks run on 2026-11-16: `ruff check`, `ruff format --check`, `pytest` (195 passed in ~12 s), `flutter analyze` (no issues), `flutter test` (3 passed), `alembic upgrade head` inside the Docker backend container on the dev database.
- Manual test steps for the owner: README §3.2.1. Open the dev database in DBeaver (`127.0.0.1:5433`, db `receiptbox`, user/password `receiptbox`), look at the 19 tables next to spec §6, run the three sample queries.
- Known gaps / follow-ups:
  - ~~CI for this phase has not run yet~~ → green on 2026-11-16, see the entry above.
  - `merchants_seed.csv` was written by Claude from general knowledge of Turkish brands; **please review** names, categories and aliases (e.g. Trendyol/Hepsiburada are `OTHER`, Decathlon is `CLOTHING`).
  - Only `observations.amount_minor`, `receipt_items.unit_price_minor` / `total_price_minor` and `products.purchase_price_minor` may be NULL (unknown amount); see D-012.
  - Merchant normalisation beyond uppercase/punctuation (legal suffixes, fuzzy match) is P06.
  - On this PC `localhost` made every database connection wait ~2 s (IPv6 first), so all database URLs use `127.0.0.1`.

### 2026-11-16 — P00 CI confirmed
- First CI run on `main` (`3ccbdb3`): jobs `backend` and `mobile` both green. This closes the last P00 acceptance criterion. The action versions noted below as unverified worked as written.

### 2026-11-15 — P00 Repository bootstrap & tooling (done locally; CI confirmed on 2026-11-16)
- Done:
  - Monorepo layout from spec §21, `.gitignore` (secrets, `ai/datasets/*`, `backend/storage/`, generated Dart), `.gitattributes`, `.editorconfig`, `.env.example`, Windows README.
  - `infra/docker-compose.yml`: `db` (postgres:16, volume, healthcheck, separate `receiptbox_test` database) and `backend` (Dockerfile, non-root, depends on healthy db).
  - Backend: uv project (Python 3.12), app factory, pydantic-settings config, async SQLAlchemy session dependency, `GET /api/v1/health`, single error handler (`{"error": {"code","message"}}`, never echoes input), JSON logging with a field whitelist (no bodies, headers or query strings).
  - Mobile: Flutter Android project (`com.receiptbox`, minSdk 24), Riverpod (codegen), go_router, Dio, `API_BASE_URL` via `--dart-define`, `tr_TR` locale, health placeholder screen ("Sunucu: bağlı").
  - `.github/workflows/ci.yml` with `backend` and `mobile` jobs.
- Tests added: `backend/tests/test_health.py` (7 tests: health ok, DB down → 503, unknown route shape, domain error shape, 500 does not leak details, validation error does not echo input, logs contain no body/query/header); `mobile/test/health_screen_test.dart` (3 widget tests: connected, database error, unreachable).
- Checks run on 2026-11-15: `ruff check`, `ruff format --check`, `pytest` (7 passed), `flutter analyze` (no issues), `flutter test` (3 passed), `docker compose up -d` + `curl /api/v1/health` → `{"status":"ok","db":"ok"}`, app on the Android emulator (Medium Phone API 37) showed "Sunucu: bağlı", and "Sunucu: bağlantı yok" after stopping the backend.
- Manual test steps for the owner: see README §3 (start Docker → `docker compose -f infra/docker-compose.yml up -d` → `curl http://localhost:8000/api/v1/health` → start the emulator → `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000`).
- Known gaps / follow-ups:
  - ~~CI has not run yet~~ → resolved on 2026-11-16, see the entry above.
  - Host port of the Docker database is **5433** (a Windows PostgreSQL 17 service already uses 5432 on the owner's PC).
  - `*.g.dart` files are git-ignored; run `dart run build_runner build` after cloning (CI does this).
  - `AI_MODEL_EXTRACT` / `AI_MODEL_ASSISTANT` / `GEMINI_API_KEY` are empty in `.env.example` until P05.
  - Flutter 3.50 deprecates `package:flutter/material.dart`; the app uses `package:material_ui/material_ui.dart` (as generated by `flutter create`).
  - Tested only on the emulator, not on a real phone (USB steps are in README §3.4).
