# ReceiptBox AI

An Android app that remembers what you bought: receipts, bank screenshots, installments, warranties and return deadlines, with an AI assistant on top.

**Stack:** Flutter (Android only) · FastAPI · PostgreSQL 16 · Docker Compose.
This is a single-semester senior design project. The current state is tracked in [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Project map

| Path | What it is |
|---|---|
| `mobile/` | The Flutter app (Android only) |
| `backend/` | The FastAPI server (`app/` code, `tests/`, `migrations/` for the database) |
| `infra/` | `docker-compose.yml`: starts PostgreSQL and the backend |
| `ai/` | AI experiments and datasets. `ai/datasets/` is git-ignored: never commit real receipts |
| `docs/` | Specification, phase plans, decisions, progress log |
| `CLAUDE.md` | Rules for Claude Code, which writes the code |
| `.claude/skills/receiptbox-scope/` | The "scope guard" skill: what is in and out of scope |

Read these before changing anything:
[`CLAUDE.md`](CLAUDE.md) · [`.claude/skills/receiptbox-scope/SKILL.md`](.claude/skills/receiptbox-scope/SKILL.md) · [`docs/PROGRESS.md`](docs/PROGRESS.md) · [`docs/spec/00_PROJECT_SPEC.md`](docs/spec/00_PROJECT_SPEC.md) · [`docs/phases/`](docs/phases/) · [`docs/DECISIONS.md`](docs/DECISIONS.md)

---

## 1. Install the tools (Windows 11, one time)

Open **PowerShell** for the commands below. After installing a tool, **close and reopen PowerShell** (and VS Code) so it finds the new program.

### 1.1 Git

```powershell
winget install --id Git.Git -e
git --version
```

### 1.2 Docker Desktop (with WSL 2)

1. Turn on virtualization in your PC's BIOS if it is off (most PCs have it on).
2. Install Docker Desktop from <https://www.docker.com/products/docker-desktop/>. Keep **"Use WSL 2 instead of Hyper-V"** ticked.
3. If Windows asks you to install or update WSL, run in an **administrator** PowerShell: `wsl --install`, then restart the PC.
4. Start **Docker Desktop** and wait until the whale icon says **Engine running**.
5. Check: `docker --version` and `docker info` (no error).

### 1.3 uv (Python package manager) and Python 3.12

```powershell
winget install --id astral-sh.uv -e
uv --version
uv python install 3.12
```

You do not need to install Python separately: `uv` downloads Python 3.12 for the backend by itself.

### 1.4 Flutter SDK

```powershell
git clone https://github.com/flutter/flutter.git -b stable C:\src\flutter
```

Then add `C:\src\flutter\bin` to your PATH: **Start menu → "Edit environment variables for your account" → Path → Edit → New**, paste `C:\src\flutter\bin`, OK. Reopen PowerShell and check:

```powershell
flutter --version
```

### 1.5 Android Studio, SDK and emulator

```powershell
winget install --id Google.AndroidStudio -e
```

1. Open **Android Studio** once. In the setup wizard choose **Standard**, accept the licenses (every license on the left), and wait for the downloads to finish.
2. Open **More Actions → SDK Manager → SDK Tools** tab. Tick **Android SDK Command-line Tools (latest)** and click **Apply**.
3. Open **More Actions → Virtual Device Manager**. A device such as *Medium Phone* or a *Pixel* should be listed. If not, click **Create Device** and pick any recent phone with a Google Play system image.
4. Accept the Android licenses (type `y` to each question):
   ```powershell
   flutter doctor --android-licenses
   ```
5. Check everything:
   ```powershell
   flutter doctor
   ```
   The **Android toolchain** line must have a green check. Warnings about *Visual Studio* or *Chrome* can be ignored: this project is Android only.

---

## 2. First-time project setup

```powershell
git clone <your-private-repo-url> receiptbox-ai
cd receiptbox-ai
copy .env.example .env
```

`.env` holds your local settings. It is git-ignored; never commit it. For P00 you do not need to change anything in it.

---

## 3. Run it (three commands)

### 3.1 Database + backend (Docker)

```powershell
docker compose -f infra/docker-compose.yml up -d
```

Check it:

```powershell
curl http://localhost:8000/api/v1/health
```

You should see `{"status":"ok","db":"ok"}`. API docs are at <http://localhost:8000/docs>.

Useful Docker commands:

```powershell
docker compose -f infra/docker-compose.yml logs backend      # see backend logs
docker compose -f infra/docker-compose.yml down              # stop everything (data is kept)
docker compose -f infra/docker-compose.yml down -v           # stop and DELETE the database data
docker compose -f infra/docker-compose.yml up -d --build     # rebuild after changing backend code
```

> **Port 5433, not 5432.** The Docker database is reachable from your PC at `localhost:5433`, so it never clashes with a PostgreSQL that is already installed on Windows.

### 3.2 Backend on your PC (for development and tests)

Use this instead of the Docker `backend` while you work on backend code. Start only the database:

```powershell
docker compose -f infra/docker-compose.yml up -d db
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Backend checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q          # needs the db container running
```

### 3.2.1 Database tables (migrations)

The tables are created by Alembic migrations (`backend/migrations/versions/`). With the database container running:

```powershell
cd backend
uv run alembic upgrade head      # creates all tables and loads the seed data
uv run alembic current           # shows the current version (0002 = up to date)
```

Or from inside the Docker backend container: `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`.

`uv run alembic downgrade base` removes every table again (and **all data** in them). The tests do this to the separate `receiptbox_test` database by themselves; you never need it for `receiptbox`.

**Look at the tables yourself:** install [DBeaver](https://dbeaver.io/download/) (Community), create a **PostgreSQL** connection with host `127.0.0.1`, port `5433`, database `receiptbox`, user `receiptbox`, password `receiptbox`, then open `receiptbox → Schemas → public → Tables`. Compare them with section 6 of `docs/spec/00_PROJECT_SPEC.md`. Handy queries:

```sql
SELECT key, label_tr, sort_order FROM categories ORDER BY sort_order;
SELECT count(*) FROM merchants;                      -- 223
SELECT a.alias_normalized, m.canonical_name
  FROM merchant_aliases a JOIN merchants m ON m.id = a.merchant_id
 WHERE a.alias_normalized = 'MIGROS TICARET AS';     -- Migros
```

### 3.2.2 Try the login system (Swagger UI)

With the backend running (after code changes: `docker compose -f infra/docker-compose.yml up -d --build`), open <http://localhost:8000/docs>. Every endpoint can be tried from this page.

1. **`POST /api/v1/auth/register`** → *Try it out* → body:
   `{"email": "ebru@example.com", "password": "Parola123", "is_adult_confirmed": true}` → *Execute*. You get **201** with an `access_token` and a `refresh_token`. (Password: at least 8 characters, one letter and one digit.)
2. Click the green **Authorize** button at the top, paste the `access_token` (no "Bearer " prefix), *Authorize*.
3. **`GET /api/v1/me`** → *Execute* → **200** with your e-mail. (Without Authorize you get **401** `AUTH_INVALID_TOKEN`.)
4. **`POST /api/v1/auth/login`** with the same e-mail and password → **200**. A wrong password gives **401** `AUTH_INVALID_CREDENTIALS`; the 6th attempt within a minute gives **429** `RATE_LIMITED`.
5. **`POST /api/v1/auth/refresh`** with `{"refresh_token": "<the refresh_token>"}` → **200**, a new pair. Copy the new `refresh_token` and refresh a second time → **200** again.
6. Now send the **first** `refresh_token` again → **401**. This is *reuse detection*: a refresh token works only once, and replaying an old one also kills the newer tokens (try the newest one: **401**).
7. **`POST /api/v1/auth/logout`** with a valid `refresh_token` → **204**; using it afterwards → **401**.
8. **`DELETE /api/v1/me`** (Authorize first) → **204**. Your account and all its data are gone: `GET /api/v1/me` → **401**, logging in → **401**.

An access token lives 15 minutes (`AUTH_EXPIRED` afterwards: use *refresh*); a refresh token lives 30 days.

### 3.2.3 Try the receipt extraction (P05)

The phone does OCR and hides personal data; the backend turns the **masked text** into a checked extraction. In the P04 debug screen ("Okunan bilgiler") the "Maskelenmiş metin" box is what the backend receives. Open <http://localhost:8000/docs> (rebuild first after code changes: `docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`).

**One-time setup for the real model:** put your key in `.env` (never commit it): `GEMINI_API_KEY=...`. The model names are settings too (`AI_MODEL_EXTRACT`, defaults in `.env.example`). The free tier may use submitted text to improve Google's products (spec 14), so only paste made-up or already-masked text.

1. **Register** and **Authorize** as in 3.2.2.
2. **`POST /api/v1/extract/receipt`** with
   ```json
   {"masked_text": "MIGROS TICARET A.S.\nTARIH: 14.11.2026   SAAT: 18:42\nSUT 1L   69,90\nEKMEK   12,50\nTOPLAM   *82,40\nKREDI KARTI   82,40", "capture_date": "2026-11-18", "source": "GALLERY"}
   ```
   → **403** `AI_CONSENT_REQUIRED`. AI extraction needs your consent (the consent screen / Settings switch send it from the app; here you do it by hand).
3. **`PUT /api/v1/me/ai-consent`** with `{"ai_consent": true}` → **200**.
4. Send step 2 again → **200** with `observation_id`, the `extraction` (merchant, date, time, total, payment method, installment count, items) and a `confidence` of `HIGH` / `MEDIUM` / `LOW` for each field. The total is `"82.40"`: the model never calculates, and every value must be found in your text.
5. Try breaking it, and look at the confidence:
   - remove the date line → `date: null`, `date: LOW` (a missing date is never guessed);
   - change `*82,40` to `*99,00` in `TOPLAM` but leave the items → items `LOW` (they do not add up);
   - a total like `1.245.000,00` → **422** `EXTRACTION_REJECTED` (absurd amount, nothing saved);
   - more than 20 KB of text → **413**; more than 20 requests in a minute → **429**.
6. `PUT /api/v1/me/ai-consent` with `false` and repeat: **403** again. Manual entry never needs the consent.

The result is saved as a `PENDING_REVIEW` observation (look at the `observations` and `receipt_items` tables in DBeaver; amounts are whole kuruş). The review screen is P07.

**Without a key or a network** (demo mode, needs the source tree, not the Docker image): run the backend from `backend/` with `AI_PROVIDER=fake`; it answers only for the 13 made-up receipts in `backend/tests/fixtures/receipts/` (paste the content of one of the `.txt` files).

**Real model on 5 made-up receipts** (prints the extraction, confidence, differences from the hand-written expectation, latency and token counts; the key is never printed):

```powershell
uv run --project backend python ai/experiments/run_extract_manual.py
```

All automated tests use the fake provider only: `AI_PROVIDER=fake` is forced in `backend/tests/conftest.py`, so `uv run pytest` never calls a real model, whatever is in your `.env`.

### 3.2.4 Try the e-invoice QR, merchants and categories (P06)

Open <http://localhost:8000/docs>. After code changes rebuild first: `docker compose -f infra/docker-compose.yml up -d --build backend` (P06 has no new migration). Register and **Authorize** as in 3.2.2. The suggestions need nothing else; the AI parts need the consent from 3.2.3 (`PUT /api/v1/me/ai-consent` with `true`).

**Merchant and category suggestions on a receipt** (`POST /api/v1/extract/receipt`, the Migros text from 3.2.3): the answer now has a `suggestions` part:
- `merchant`: `match` is `GLOBAL_ALIAS` and `canonical_name` is `Migros` (a known merchant); `FUZZY` for a close spelling, `NEW` for an unknown shop (only a proposed name, nothing is created), `NONE` without a name.
- `category`: `key` `GROCERY`, `source` `MERCHANT_DEFAULT` (the seeded category). For an unknown shop the source is `LLM` (the model chose the category) and, if the model fails, `OTHER` with `FALLBACK`.
Try a name you know in several spellings in the text (`MİGROS TİCARET AŞ`, `MIGROS MAGAZACILIK 1234 KONYA`, `SHELL&TURCAS`) and look at `canonical_name`.

**e-Archive / e-Invoice QR** (`POST /api/v1/extract/einvoice-qr`), body:
```json
{"qr_payload": {"ettn": "11111111-2222-3333-4444-555555555555", "vkntckn": "9876543210", "senaryo": "EARSIVFATURA", "tarih": "14-11-2026", "no": "ORN2026000000456", "parabirimi": "TRY", "malhizmettoplam": "2118.64", "vergidahil": "2499.00", "odenecek": "2499.00"}, "capture_date": "2026-11-18"}
```
- **200**: `extraction.total` is `"2499.00"`, `date` `"2026-11-14"`, `confidence.total` and `date` are `HIGH`, `merchant` is `LOW` (the QR holds no merchant name), `ai_used` is `false`. No AI is called, so it also works **without** the AI consent.
- Add `"masked_text": "ORNEK ELEKTRONIK TICARET A.S.\nKULAKLIK BLUETOOTH 2.118,64\nODENECEK TUTAR 2.499,00"` (with the consent on): the AI adds merchant name and items, `ai_used` is `true`; total and date still come from the QR.
- Send `"avkntckn": "12345678901"` too (the buyer's identity number): it is dropped and nowhere in the answer or the database.
- Try breaking it: `"qr_payload": "not json"` or `{"wifi": "x"}` → **422** `QR_INVALID`; `"parabirimi": "USD"` → **422**; `"odenecek": "1.245.000,00"` → **422** `EXTRACTION_REJECTED`.

**On the emulator (debug build): the synthetic e-Archive invoice with a QR code**
1. Put the sample on the emulator (made-up invoice, see 3.3 for generating samples): `adb push ai/datasets/synthetic/einvoice_qr.pdf /sdcard/Download/`
2. Files app → Downloads → long-press `einvoice_qr.pdf` → **Share** → **ReceiptBox AI** → **Fiş veya fatura**.
3. The result screen says **"e-Fatura QR kodu bulundu"**, hides the name and the T.C. kimlik no (`[NAME]`, `[TCKN]`).
4. Scroll down: **Sunucu (yalnızca debug)** → **Sunucuya gönder (debug)**. Signed in, with the AI switch in Settings on (QR works without it too), you see: source "e-Fatura QR + metin", total **2499.00 TL**, date **2026-11-14**, a merchant and category suggestion ("Teknoloji (yapay zekâ)") and the confidence of each field. With the Settings switch off the answer says "yapay zekâ kullanılmadı" and has no merchant or items.
5. Do the same with a normal receipt photo (Galeriden Ekle): the panel sends the masked text to `/extract/receipt` and shows the suggestions; with the Settings switch off it says that AI reading is off and sends nothing.

This panel exists in debug builds only; the real review screen is P07.

### 3.3 The Android app

1. Start an emulator: Android Studio → **Virtual Device Manager → ▶**, or `flutter emulators --launch <emulator_id>`. Wait until you see the Android home screen.
2. Make sure the backend is running (step 3.1).
3. In another PowerShell:
   ```powershell
   cd mobile
   flutter pub get
   dart run build_runner build
   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
   ```

The first build takes several minutes (Gradle downloads things).

**What you should see (P03):**

1. First launch: the consent screen **"Verilerin senin kontrolünde"** → tap **Kabul ediyorum** (or "Şimdilik kabul etmiyorum").
2. **Hesap oluştur** (Register): enter an e-mail and a password (8+ characters, a letter and a digit), tick **"18 yaşından büyük olduğumu onaylıyorum"**, tap **Kayıt ol**. Without the tick you get a red message and nothing is sent.
3. You land on **Ana Sayfa** with the bottom bar: Ana Sayfa · Harcamalar · **(+)** · Ürünler · Asistan. Tap each tab. Tap the raised **(+)** button: a sheet with Fiş Tara, Galeriden Ekle, Banka Ekran Görüntüsü, Manuel Harcama, Ürün Ekle. Since P04 the first three are real (see below); Manuel Harcama and Ürün Ekle still open a "Bu özellik yakında" page (the arrow goes back).
4. The gear icon at the top right of Ana Sayfa opens **Ayarlar**: your e-mail, the **"Fiş görsellerini sakla"** switch (on by default), "Sunucu: bağlı", **Çıkış yap** and **Hesabı sil**.
5. Close the app completely and open it again: you are still signed in (no login screen).
6. **Çıkış yap** → Login screen. Sign in again → Ana Sayfa.
7. **Hesabı sil** → confirmation → the account is deleted and you are back on **Register**. (Signing in with the old e-mail now fails: "E-posta veya parola hatalı.")

`10.0.2.2` is the emulator's special address for "the PC it runs on".

**Capture on the emulator (P04).** A real phone is not needed: everything below uses pictures and files that you put on the emulator. Nothing is uploaded in P04; the phone reads the picture, hides personal data and shows the result on a screen ("Okunan bilgiler"). Debug builds also show the original text under the masked text, so you can compare. Release builds never keep the original text.

1. Make synthetic samples (made-up receipt, bank screenshot, GİB QR invoice, 2-page PDF; they go to the git-ignored `ai/datasets/synthetic/`):
   ```powershell
   uv run --with pillow --with "qrcode[pil]" python ai/experiments/make_synthetic_samples.py
   ```
2. Put them in the emulator's gallery and downloads (the emulator must be running):
   ```powershell
   adb push ai/datasets/synthetic/. /sdcard/Pictures/ReceiptBoxSamples/
   adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/ReceiptBoxSamples/receipt_market.jpg
   adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/ReceiptBoxSamples/bank_screenshot.jpg
   adb push ai/datasets/synthetic/invoice_2pages.pdf /sdcard/Download/
   ```
3. **Gallery:** (+) → **Galeriden Ekle** → **Fotoğraf seç** → pick `receipt_market.jpg` → choose **Fiş veya fatura**. You should see "3 hassas bilgi gizlendi: 1 telefon, 1 isim, 1 kart numarası", the phone number as `[PHONE]`, the customer as `[NAME]`, the card as `[CARD]`, and **TOPLAM 270,30** still readable. Scroll down: the original text is shown below (debug builds only).
4. **Bank screenshot:** (+) → **Banka Ekran Görüntüsü** → pick `bank_screenshot.jpg`: the balance line, IBAN, card number and account holder are replaced; the spending rows stay.
5. **Share:** open the emulator's **Files** app → Downloads → long-press `invoice_2pages.pdf` → **Share** → **ReceiptBox AI** → choose the kind. "2 sayfa okundu", the name after "Sayın" is `[NAME]`. (The same works from any app's share button, also while you are signed out: the file waits and is offered after you sign in.)
6. **Camera:** (+) → **Fiş Tara**. The first time Android asks for the camera permission. "Don't allow" shows an explanation and a **Galeriden ekle** button. The emulator's virtual scene shows a living room: take a picture and you get "Okunamadı" (there is no text in it); **Tekrar dene** goes back to the camera. A real receipt through a real phone camera is still to be checked (see `docs/PROGRESS.md`, known gaps).
7. **Offline:** switch the emulator to airplane mode and repeat step 3: it works the same (the OCR models are inside the app).

**Real ML Kit test on the emulator** (`mobile/integration_test/capture_e2e_test.dart`): reads the six synthetic samples with the real OCR/QR/PDF code and checks the masking and that the buyer's identity number is removed from the GİB QR. `flutter test` reinstalls the app, which wipes files pushed to the emulator, so the samples are served from your PC for a moment:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory ai/datasets/synthetic
```

and in a second PowerShell:

```powershell
cd mobile
flutter test integration_test/capture_e2e_test.dart -d emulator-5554
```

Add `--dart-define=EXPECT_OFFLINE=true` to prove it works without a network: the test prints `SAMPLES_READY` and waits; run `adb shell cmd connectivity airplane-mode enable`, and it continues once the network is really gone. Turn airplane mode off afterwards (`adb shell cmd connectivity airplane-mode disable`). Do not use `adb` screenshot loops while it runs.

Mobile checks:

```powershell
flutter analyze
flutter test
```

**End-to-end test on the emulator** (drives the real app against the real backend and checks the acceptance criteria: consent → register → Home, restart keeps the session, an expired access token is renewed silently, a revoked refresh token leads to Login, logout, delete account). It needs the emulator running and `docker compose ... up -d` running; it creates a throw-away `e2e-...@example.test` account and deletes it again. It is not part of CI.

```powershell
cd mobile
flutter test integration_test/app_e2e_test.dart -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Do not take screenshots with `adb` in a loop while it runs: that disturbs the test.

**Design:** all colors, font sizes, spacing, radii and component sizes live only in `mobile/lib/core/theme/` (values from the Figma file, see `docs/design/DESIGN_TRACK.md`). A test (`mobile/test/theme_tokens_guard_test.dart`) fails if a hard-coded value is written anywhere else.

`dart run build_runner build` generates the `*.g.dart` files (Riverpod providers). They are git-ignored, so run it after cloning and after changing a provider.

### 3.4 Your real phone over USB (later)

1. On the phone: **Settings → About phone →** tap **Build number** 7 times, then **Settings → Developer options → USB debugging: on**.
2. Plug in the cable and accept the "Allow USB debugging" prompt. Check: `adb devices` should list your phone as `device`. (`adb` is in `%LOCALAPPDATA%\Android\Sdk\platform-tools`.)
3. Let the phone reach the backend on your PC through the cable:
   ```powershell
   adb reverse tcp:8000 tcp:8000
   ```
4. Run with a different address:
   ```powershell
   flutter run --dart-define=API_BASE_URL=http://localhost:8000
   ```

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| `flutter`, `uv` or `docker` "is not recognized" | Close and reopen PowerShell / VS Code. Then check your PATH (see 1.4). |
| `docker ... failed to connect to the docker API` | Docker Desktop is not running. Start it and wait for **Engine running**. |
| `port is already allocated` on 8000 | Something else uses port 8000. Stop it, or change the port mapping in `infra/docker-compose.yml`. |
| `pytest` cannot connect to the database | Start it: `docker compose -f infra/docker-compose.yml up -d db`. Tests use `127.0.0.1:5433`. |
| Database connections are slow (about 2 seconds each) | Use `127.0.0.1` instead of `localhost` in the database URLs (some Windows PCs try IPv6 first). The defaults already do. |
| App shows "Sunucu: bağlantı yok" | Is the backend running? Open <http://localhost:8000/api/v1/health> in your PC browser. On a real phone use `adb reverse` (3.4). |
| Emulator is very slow or does not start | Run `emulator -accel-check` from `%LOCALAPPDATA%\Android\Sdk\emulator`. Make sure virtualization is on in BIOS and "Windows Hypervisor Platform" is enabled in Windows Features. |
| `flutter doctor` complains about Android licenses | `flutter doctor --android-licenses` |

---

## 5. Secrets and private data

- `.env` is never committed. `.env.example` lists every setting with placeholder values only.
- `ai/datasets/` and `backend/storage/` are git-ignored. **Never commit real receipts, real bank screenshots or personal data.**
- Docker Compose uses an obviously fake development JWT secret (`infra/dev-defaults.env`). Put your own in `.env` for anything beyond local development.

## 6. Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and on pull requests:

- **backend:** `uv sync`, `ruff check`, `ruff format --check`, `pytest` (with a PostgreSQL service)
- **mobile:** `flutter pub get`, `build_runner`, `flutter analyze`, `flutter test`

## 7. Commit messages

`P07: add receipt review confirm endpoint` (phase number first). See [`CLAUDE.md`](CLAUDE.md) for the full conventions.
