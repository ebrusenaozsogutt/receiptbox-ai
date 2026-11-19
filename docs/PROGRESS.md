# Progress

Update after every phase. Newest entry on top of the log.

## Status board

| Phase | Title | Status | Date done |
|---|---|---|---|
| P00 | Repository bootstrap & tooling | ✅ Done | 2026-11-16 |
| P01 | Backend data model & migrations | ✅ Done | 2026-11-16 |
| P02 | Backend authentication | ✅ Done | 2026-11-16 |
| P03 | Mobile app shell & auth | ✅ Done | 2026-11-16 |
| P04 | On-device capture: OCR, QR, PII masking, share | ✅ Done | 2026-11-19 |
| P05 | AI provider layer & receipt extraction | ✅ Done (CI pending) | 2026-11-19 |
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

### 2026-11-19 — P05 AI provider layer & receipt extraction (done locally; CI pending)
- Done:
  - **Provider layer (`backend/app/ai/`)**: `AIProvider` protocol and `get_provider()`; `GeminiProvider` (`google-genai`, constrained JSON output, 1 retry on invalid schema, back-off 1/2/4 s on 429 and 5xx inside one 30 s budget, model and key from settings, one log line per call with provider, model, prompt version, latency and token counts and never the content); `FakeProvider` (answers from fixtures by a hash of the text, used by all tests and `AI_PROVIDER=fake`); prompt `prompts/receipt_extract.v1.md` (copy exactly, null when absent, no arithmetic, Turkish receipt conventions); the other three provider methods raise `NotImplementedError`.
  - **Validation (`app/ai/validation.py`)**: every rule of spec 5.3 and the HIGH/MEDIUM/LOW levels of 5.4. The model returns strings; amounts, dates and times are parsed in code and must be found in the text. A missing date stays `null` (LOW), never guessed. An absurd total rejects the extraction. See DECISIONS P-040, P-044.
  - **`POST /api/v1/extract/receipt`** `{masked_text, capture_date, source}` → `{observation_id, extraction, confidence}`; saves a `PENDING_REVIEW` observation with items in kuruş, `extraction_json`, `field_confidence_json`, `masked_text`, the spec 7.2 fingerprint and the prompt version. 20 requests/min/user, 20 KB limit; errors `AI_CONSENT_REQUIRED` (403), `TEXT_TOO_LARGE` (413), `EXTRACTION_REJECTED` (422), `EXTRACTION_FAILED` (502); nothing is saved on those.
  - **AI consent enforced (the P04 known gap)**: `users.ai_consent` (migration 0003), `PUT /me/ai-consent`, 403 without it; the app sends the device's choice to the server at sign-in/start and has a new Settings switch "Yapay zekâ ile fiş okuma"; manual entry is not gated (P-041).
  - **13 synthetic masked receipts** with fake-model answers and hand-written expected results in `backend/tests/fixtures/receipts/` (Migros, BİM, A101 with a discount, restaurant with service charge, pharmacy, electronics with `TAKSİT SAYISI`, no date, items that do not add up, fuel, a future date, an invented total, an absurd total that is rejected, a merchant name below the header). Real receipt texts go to `ai/datasets/` later (git-ignored).
  - `ai/experiments/run_extract_manual.py` runs the real model on made-up receipts and prints results and latency.
- Tests added: backend **438 tests** (was 285): `test_validation.py` (67: every rule passing and failing + all fixtures), `test_gemini_provider.py` (22, with a stand-in SDK client: retry, back-off, time budget, logging without content, settings), `test_extraction_service.py` (15), `tests/api/test_extract_receipt.py` (every fixture end to end, 401/403/413/422/429/502, per-user quota, logs contain no receipt text), `tests/api/test_ai_consent.py`, `test_no_provider_leak.py` (ast import check). Flutter **355 tests** (was 345): consent sync and the Settings switch. All tests use `FakeProvider`; `conftest.py` forces `AI_PROVIDER=fake`.
- Checks run on 2026-11-19: `ruff check`, `ruff format --check`, `pytest` (438 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (355 passed).
- **Real Gemini (manual run, synthetic receipts, `gemini-3.5-flash-lite`)**: 5 receipts (Migros, BİM, restaurant, electronics with 6 installments, no date). Every answer that came back matched the hand-written expectation, all fields HIGH except the missing date/time (LOW, `null`). One run of the no-date receipt split "DOMATES 2 KG" into name "DOMATES" + quantity 2 (a sensible difference, not an error). Latency 2.2-12.8 s per receipt (average about 7-11 s; tokens about 1200 in / 200-320 out). Not every call succeeded: in the first run two receipts failed with a provider error (503 "overloaded") that was fine on the next try, and in the last run one hit the 30 s limit; the API answers `EXTRACTION_FAILED` then and the user enters the receipt by hand. Also tried end to end through the running Docker backend (register → 403 → consent → 200 in 7.5 s → delete account).
- Manual test steps for the owner: README §3.2.3 (Swagger), plus the manual run command there.
- Known gaps / follow-ups:
  - Only synthetic fixtures; **real receipt texts are not tried yet**. Extraction quality on real, messy OCR text is unknown until the owner's real masked texts are added under `ai/datasets/` (P15 measures it).
  - Gemini free tier: variable latency (2-13 s), occasional 503, a 30 s budget that is sometimes used up; the free tier may use submitted text for Google's product improvement (spec 14), so only synthetic text was sent. The free-tier daily limits are unverified (third-party pages only). `AI_THINKING_LEVEL=MINIMAL` looked faster once (3.7 s against 9.4 s) but was not measurable through the noise, so it is off.
  - The mobile app does not call the endpoint yet (the review flow is P07); it only syncs and enforces the consent. P07 must show a progress state of up to about 30 s and the manual-entry fallback on `EXTRACTION_FAILED` / `AI_CONSENT_REQUIRED`.
  - A device that declined on the consent screen switches the server's copy off at sign-in, even if another device had accepted: the latest choice on the signing-in device wins.
  - The fingerprint uses only the first step of merchant normalisation; P06/P09 may recompute it. Duplicate detection (P09) does not exist yet: the same receipt twice makes two observations with the same fingerprint.
  - Discount lines are not stored as items (the database has no negative amounts); they only count in the sum check.
  - `AI_PROVIDER=fake` works from the source tree only (the Docker image does not contain the test fixtures).
  - CI for this phase has not run yet (push pending).

### 2026-11-19 — P04 CI confirmed
- CI run on `main` (`8f35836`): jobs `backend` and `mobile` both green (the mobile job runs `build_runner`, `flutter analyze` and the 345 Flutter tests on GitHub's runner; the emulator test is not part of CI). P04 is closed; the real-phone camera check stays open under known gaps.

### 2026-11-19 — P04 On-device capture: OCR, QR, PII masking, share (done locally; CI confirmed later the same day; verified on the emulator, no real phone)
- Done:
  - **Pipeline (`features/capture/data/capture_pipeline.dart`)**, entirely on the phone and offline: image or PDF (first 2 pages via `pdfx`) → resize to a 2000 px long edge + EXIF rotation into a new metadata-free JPEG → GİB QR (ML Kit barcode, only a GİB invoice QR is kept, buyer `avkntckn` removed) → ML Kit text recognition (Latin, text lines joined in reading order: a name and its price on the same band become one row) → PII masking → `CapturePayload {kind, masked_text, qr_payload?, capture_date, source}`. Nothing is uploaded and no image is stored (P07); every temporary image is deleted when processing ends and the temp folder is cleared at the next start.
  - **PII masker (`core/privacy/pii_masker.dart`)** with all spec 15.1 rules: IBAN, Luhn card numbers (also partly hidden), TCKN with checksum, phones, e-mails, balance/limit/account lines (whole line), names after Sayın / Ad Soyad / Kart Sahibi / Müşteri (+ Hesap Sahibi, see P-035). Turkish-aware (İ/ı/ş folding, length-preserving), biased toward masking, returns counts only.
  - **Screens:** Fiş Tara (live preview, guide frame, shutter; permission denied / no camera / error states with a way to the gallery), Galeriden Ekle and Banka Ekran Görüntüsü (system photo picker, no permission), a "Bu bir ne?" sheet (receipt or bank screenshot) for gallery and shared files, and **Okunan bilgiler** (masked text, how many items of each kind were hidden, QR found, and in debug builds the original text under it with a warning). Share sheet: images and PDFs (`SEND`/`SEND_MULTIPLE` intent filters); shared files wait in an app-wide inbox if you are still signed out.
  - Android: camera permission (camera not a required feature), `launchMode=singleTask`, `compileSdk 37` (needed by `receive_sharing_intent`), Flutter deep linking switched off (P-036).
  - `ai/experiments/make_synthetic_samples.py` makes six SYNTHETIC samples (receipt, rotated receipt, receipt with GİB QR, bank screenshot, 2-page PDF, an image without text) into the git-ignored `ai/datasets/synthetic/`. No real receipt or bank screenshot was used or committed.
- Tests added (**345 Flutter tests**, was 192): `pii_masker_test` (84 cases incl. false positives: totals, dates, times, seller tax numbers, 11-digit numbers failing the TCKN checksum, "MÜŞTERİ NÜSHASI"), `gib_qr_parser_test` (23), `reading_order_test`, `image_preprocessor_test` (scaling, EXIF, no metadata), `capture_pipeline_test` (fakes: masking, QR, PDF, errors, files deleted also on failure, original text only when debug asks), `capture_screens_test` (gallery, bank, kind sheet, picker cancel/error, result states, share at start / while running / while signed out, camera states), `privacy_guard_test` (no logging and no network code in `core/ocr`, `core/privacy`, `features/capture`; the original text is kept only for debug), and the theme-token guard still passes. Widget tests use a fake pipeline; no real LLM anywhere.
- Checks run on 2026-11-19: `ruff check`, `ruff format --check`, `pytest` (285 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (345 passed).
- **Verified on the Android emulator** (Medium Phone API 37, synthetic samples only):
  - `integration_test/capture_e2e_test.dart` with the REAL ML Kit, PDF and image code: 6/6 pass (receipt text read and masked; EXIF-rotated photo read upright; GİB QR found with the buyer TCKN absent; bank screenshot IBAN/balance/card/holder masked; 2-page PDF read; picture without text gives "no text"). It also passes **in airplane mode** (the test waits until the network is really gone before it reads anything): the phase works offline.
  - By hand in the real app: gallery → kind sheet → masked result; bank screenshot; **share** a picture and a PDF with `adb` share intents and from the emulator's **Files app → Share → ReceiptBox AI** (while running, from a cold start, and while signed out: offered after login); camera permission denied screen, live preview (emulator virtual scene), shutter, "no text" result and retry.
  - The throw-away test accounts were deleted again; the dev database only holds `ebru@test.com`.
- Manual test steps for the owner: README §3.3 "Capture on the emulator (P04)".
- **Code-review note (acceptance: original text never persisted or sent):** the unmasked OCR text is created in `OcrService.readText` and consumed in `CapturePipeline.process`, which masks it immediately. It is not written to disk, SharedPreferences or logs (no `print`/`debugPrint`/`log` in the guarded folders, enforced by a test), not sent anywhere (no network package in those folders, enforced by a test, and no upload exists in P04), and `CaptureResult.debugOriginalText` is only filled when `kDebugMode` is true (a release build drops it after masking; the result screen shows it only in debug builds). In debug builds it stays in memory until the result screen is left (the flow state is reset then). Error messages shown to the user never contain image text. `allowBackup` stays off.
- Known gaps / follow-ups:
  - **Camera on a real phone is NOT checked (owner has no phone connected). Manual test for later:** on the phone run the app, (+) → Fiş Tara, allow the camera, photograph a real receipt held inside the guide frame (also a long, curved thermal receipt and a poorly lit one), and compare the masked text with the original in the debug view. The code path (preview, capture, pipeline) is the same one the emulator camera and the gallery use, but autofocus, low light and the phone's native resolution are untested.
  - **OCR quality on real receipts is not measured.** Only synthetic images were used, so the masker's real-world recall (names especially: it is a heuristic) and OCR mistakes (for example ML Kit read "ŞTİ" as "ŞTỈ" with a combining dot, "SÜT" as "sÜT") are unknown until the owner's manual check with real receipts (phase file, "Manual check for the owner": 10 receipts and 2 bank screenshots).
  - `pdfx` applies the old Kotlin Gradle plugin; Flutter warns that future versions will refuse it (the build works today). Revisit when a newer `pdfx` exists.
  - `receive_sharing_intent` crashes the app if another app shares a `content://` file without granting read access (it throws inside the plugin); normal share sheets always grant it. Only the first of several shared files is read; PDFs: first 2 pages only.
  - `capture_date` for a shared file is the copy's modified time (see P-038). The gallery picker's file time is used when Android provides it.
  - On this emulator the photo picker needed a "Done" tap after choosing a picture; real phones may select straight away.
  - Images are not kept after reading (storing receipt images is P07); the "Fiş görsellerini sakla" setting has no effect yet. The AI consent value is now enforced (P05).
  - The first Gradle build after adding the plugins took about 14 minutes on this PC; later builds take 1–2 minutes.
  - ~~CI for this phase has not run yet~~ → green on 2026-11-19, see the entry above.

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
