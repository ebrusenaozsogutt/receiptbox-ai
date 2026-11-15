# P03 — Mobile App Shell & Auth

**Goal:** A navigable Flutter app with auth, consent, theme tokens and empty feature screens.
**Depends on:** P02 · **Week:** 2
**Read first:** spec §2 (target users), §15.3 (consent), §17 · `docs/design/DESIGN_TRACK.md`

## Scope

1. Folder structure from spec §17. Theme in `core/theme/` with **placeholder tokens** (replaced when design is approved; tokens are the only place colors/sizes are defined).
2. Dio client with auth interceptor: attaches access token, refreshes once on 401, logs out on refresh failure. Tokens in `flutter_secure_storage`.
3. Screens: Splash (token check) → Consent (first run; Turkish text from spec §15.3; stored in shared_preferences) → Login / Register (18+ checkbox required) → Main shell.
4. Main shell: bottom navigation **Ana Sayfa · Harcamalar · (+) · Ürünler · Asistan**; (+) opens a bottom sheet with the 5 actions (Fiş Tara, Galeriden Ekle, Banka Ekran Görüntüsü, Manuel Harcama, Ürün Ekle) routing to placeholder screens.
5. Settings screen (from Home app bar): logout, delete account (confirm dialog), "Fiş görsellerini sakla" toggle (local setting for now).
6. Shared widgets: `MoneyText` (minor → `1.349,90 TL`), `DateText` (`09 Kasım 2026`), `EmptyState`, `ErrorView`, `LoadingView`.
7. Error handling: backend error codes mapped to Turkish messages in one place.

## Out of scope

Camera, OCR, any real data screen content.

## Acceptance criteria

- [ ] Fresh install: consent → register → lands on Home; restart keeps session.
- [ ] Expired access token silently refreshed; revoked refresh → back to Login.
- [ ] Delete account works and returns to Register.
- [ ] All 5 tabs/actions navigate; no hard-coded colors outside `core/theme/`.
- [ ] `flutter analyze` clean; widget tests pass.

## Tests

Widget tests: login validation, register 18+ checkbox, `MoneyText` formatting (≥ 6 cases), interceptor refresh logic (mocked Dio).

## Manual check for the owner

Run on emulator/phone; go through register, logout, login, delete account.
