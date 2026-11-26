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

This panel exists in debug builds only; the real review screen arrived in P07 (3.2.5) and the panel is reachable from its debug link.

### 3.2.5 Try the review flow, manual entry and documents (P07)

After pulling this phase rebuild the backend and apply the new migration (`receipt_items.position`): `docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`. Rebuild and reinstall the app too (3.3). The AI switch in Settings must be on for receipts to be read.

**On the emulator or a phone (debug build)**
1. Put the synthetic samples in the gallery (see 3.3 / `ai/datasets/synthetic/`), then **(+) → Galeriden Ekle → Fotoğraf seç → Fiş veya fatura**. Wait up to about a minute: **"Fiş okunuyor…"** (the **İptal** button stops it).
2. **"Fişi kontrol et"** opens. Fields the app is sure about have a green check; the ones it is not sure about have **KONTROL ET** on a warm background and the banner counts them. Type in a flagged field: its badge disappears and the count goes down. Open **Kalemler**: the last line says whether the items add up to the total.
3. Change the **category** and press **Kaydet**: the question **"Bu mağaza için hep böyle olsun mu?"** appears *before* anything is saved. Answer **Evet, hep böyle**.
4. You land on **Harcamalar** ("Harcama kaydedildi."). The purchase has a paperclip (the receipt picture). Open it: amount, category, evidence chip **Fiş**, items, the picture (tap it: full screen, pinch to zoom).
5. Add the **same receipt again**: the category is already the one you chose, nothing is flagged for it. (Use another merchant to start fresh; there is no matching yet, so the same receipt twice is two purchases.)
6. **Vazgeç** (or the back arrow) asks "Kaydetmeden çıkılsın mı?"; **Çık** rejects the receipt (`observations.status = REJECTED`).
7. Share `einvoice_qr.pdf` to the app (3.2.4): the card says **e-Fatura PDF**, the channel is **Online**; after saving, the detail shows the chip **e-Fatura** and the PDF's first page.
8. Switch the AI switch off in Settings and add a receipt: the form opens empty with "Yapay zekâ ile okuma kapalı…"; fill merchant and total and save (a **Manuel** purchase, the picture is still kept).
9. **Harcamalar**: try the **Kategori** and **Tarih** filters, the search box, and check that the count and total under the filters are the sum of the rows you see. **+** (top right) or **(+) → Manuel Harcama** adds a purchase by hand. In a detail: the pencil edits, the bin deletes (after a question).
10. Settings → switch **Fiş görsellerini sakla** off: a new receipt is saved without a picture.

**Swagger** (<http://localhost:8000/docs>, Register and **Authorize** as in 3.2.2): `POST /api/v1/transactions` with `{"merchant_display": "Bakkal", "date": "2026-11-14", "total_minor": 1250, "category_key": "GROCERY", "channel": "IN_STORE"}` → 201; `GET /api/v1/transactions?category=GROCERY&q=bak` finds it (answer has `count` and `sum_minor`); `POST /api/v1/documents` (multipart: a jpg or pdf under 10 MB, `type`, `transaction_id`) → 201 and the file is in the `storage` volume; `POST /api/v1/documents/{id}/access-token` then open the returned address (after 5 minutes: 401). Everything of another user answers 404.

### 3.2.6 Try the bank screenshot import (P08)

Rebuild the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`) and reinstall the app (3.3). No new migration. The AI switch in Settings must be on. Supported banks (bank-specific hints): **Garanti BBVA** (also the Bonus cards), **Kuveyt Türk**, **Akbank**. Other banks are read without hints.

**On the emulator or a phone (debug build)**
1. Put a screenshot of your card transactions in the gallery. **(+) → Galeriden Ekle → Fotoğraf seç → Banka ekran görüntüsü**. The screenshot is read **on the phone** (OCR + masking); only the masked text goes to the server. The blue note says so.
2. **"Banka ekran görüntüsü"** opens: the bank is detected from the text (the **Banka** chip; tap it to change, the screen is read again), then one card per purchase: merchant, date, amount, installment chip (`1/3`, `3 taksit`). Compare the rows and amounts with the screenshot.
3. Untick rows you do not want, tap the pencil to fix a merchant, amount, date or category, then **Seçilenleri Kaydet**. "N harcama kaydedildi." and the purchases appear in **Harcamalar** (evidence chip **Banka**).
4. Special rows: card-bill payments ("Kart Ödemesi", "Ödeme - Teşekkür") are listed under **Atlanan satırlar** as "Kart ödemesi" and never saved; refunds (`+`, "İade") are under **Olası iadeler** and are not saved as purchases (P12 handles refunds); loyalty-point rows and 0,00 TL rows are dropped; a **current-account** screen ("Hesap Hareketleri") answers "Bu ekran kart hareketi değil".
5. Import the **same screenshot twice** (or two overlapping ones): the second time the rows are under **Daha önce eklenmiş** and are not selected.
6. The screenshot is never saved or uploaded; the masked text is kept on the server for 30 days (for the evaluation) and then deleted at the next backend start.

**Swagger** (Register and **Authorize** as in 3.2.2): `POST /api/v1/extract/bank-screenshot` with `{"masked_text": "…", "bank_hint": "garanti", "capture_date": "2026-11-21"}` (use made-up text, never a real screenshot) → rows, `skipped`; `POST /api/v1/observations/confirm-batch` with `{"ids": ["<observation_id>"]}` (optional `edits` per id) saves them. Another user's observations answer 404.

**Real model, masked text only (optional)**: `uv run python ../ai/experiments/run_bank_extract_manual.py` reads `ai/datasets/bank_masked` (git-ignored) and prints per-file accuracy; `--no-hints` shows the unseen-bank behaviour.

### 3.2.7 Try the matching of receipts and bank rows (P09)

Rebuild the backend and apply the new migration (`match_decisions.merge_snapshot`): `docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`. Rebuild and reinstall the app (3.3). The thresholds are in `.env` (`MATCH_AUTO=95`, `MATCH_SUGGEST=70`, `MATCH_RECORD_MIN=50`; the defaults are fine).

**How the score works** (0-100): amount 50 (equal; 0 at a 2 % difference), date 20 (same day; 12 for one day apart; 5 for two or three), merchant 20 (the same shop, or how alike the names are), time 10 (only when both records have one: 5 minutes apart is full, 60 minutes is 0). A feature that cannot be known (a bank row has no time) is left out and the rest is scaled to 100. From **95** (and one single candidate) the two are merged at once with **Geri al**; from **70** the app asks; below, it is a new purchase.

**On the emulator or a phone (debug build)**
1. Import a bank screenshot (README 3.2.6) and **save** the rows (**Seçilenleri Kaydet**).
2. Scan a **receipt for one of those rows** (same shop, same amount, same day; for a clear merge the receipt time within a few minutes of the bank row's, or no time on the bank row). On **Kaydet** the snackbar says **"Bu fiş mevcut bir harcamayla eşleşti ve birleştirildi."** with **Geri al**. Harcamalar shows ONE purchase (the receipt's merchant and category win); the purchase is counted once in the total (the receipt's amount; a bank amount that differs a little stays evidence). Open it: **Birleşmiş kayıtlar** lists the receipt and the bank row (with the bank's own amount) and each has **Ayır**.
3. **Geri al** (or **Ayır**) gives two purchases back; the total is then the two of them (the app cannot know they are one shop visit any more).
4. A **near match** (the receipt dated one day after the bank row, no times): after **Kaydet** the sheet **"Aynı harcama olabilir mi?"** opens with the two records side by side: **Birleştir** or **Ayrı kalsın** (then both stay purchases). Close the sheet without answering and Harcamalar shows **"1 eşleşme önerisi bekliyor"**; tap it to answer.
5. The other way round: scan the receipt first, then import the bank screenshot: the matching row shows **Eşleşti** (or **Olası eşleşme**) before you save, and saving merges it or asks.
6. Two identical coffees in one bank screenshot stay **two** purchases; a receipt for one of them asks which one.
7. A row with an installment marker (`1/3`) is never merged this way; it is a payment of a plan (3.2.8).

**Swagger** (Register and **Authorize** as in 3.2.2): `GET /api/v1/matches` lists the suggestions waiting (with `score` and `features`), `POST /api/v1/matches/{id}/accept` / `/reject` answer one, `POST /api/v1/transactions/{id}/unmerge` with `{"observation_id": "…"}` separates a record. The stored candidates and their features are in the table `match_decisions` (the data of the evaluation in P15). Everything of another user answers 404.

### 3.2.8 Try the installments (P10)

No new migration. Rebuild the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`) and the app (3.3).

**The idea.** An installment purchase is **one spending** (the full total, counted once, in the month you bought it) and **N payments** (one per month). The bank rows `2/6`, `3/6` ... are those payments: they are attached to the purchase and never add spending. How the banks show them: **Garanti / Bonus** and **Akbank** show a row per month with `k/n` (the row date is assumed to be the month charged); **Kuveyt** prints the original purchase date on every row. Please compare with two real months of your own statements and tell me what you see (DECISIONS P-073 / P-074).

**On the emulator or a phone (debug build)**
1. **A slip with installments.** Scan a slip that says `TAKSIT SAYISI: 6` (or any slip, then switch **Taksitli** on and pick the count with + / -). Save. Harcamalar shows ONE purchase with the **TAKSİT** badge. Open it: the **Taksit** card lists 6 payments (12.499,00 TL = 2.083,17 x 5 + 2.083,15), each with a dot: filled = seen on a bank statement, soft = taken as paid, empty = not seen yet.
2. **The bank rows.** Import a card list that has the rows `1/6` and `2/6` of that purchase. Before saving, each row shows **TAKSİT 2/6** and "Taksit 2/6 → MediaMarkt alışverişine bağlanacak". Save: "N taksit mevcut alışverişe bağlandı"; the number of purchases and the total do not change; the two dots are filled.
3. **Taksitler** (the calendar icon on Harcamalar): the months, what is due in each, **Kalan taksit toplamı**, and which payments were seen. These are payments, not spending.
4. **A row `2/6` with no receipt:** the review says "tahmini alışveriş oluşturulacak". Saving makes a purchase marked **TAHMİNİ** (total = 6 x the row amount, date about a month earlier). Then scan its receipt: it merges ("... eşleşti ve birleştirildi"), TAHMİNİ disappears and the receipt's date and total win. The purchase is never counted twice.
5. **A row without a marker** whose amount is a sixth of a purchase of the same shop: the review says "Bir taksit olabilir (...): kaydedince sorulacak". Saving opens **"Bu bir taksit olabilir mi?"**: **Bağla** (becomes a payment, no new purchase) or **Ayrı kalsın** (a purchase of its own).
6. **A purchase you already saved:** open it, **Taksitli yap**, pick the count. **Taksit sayısını değiştir** works until a bank row is on the plan; **Planı iptal et** removes its payments from Taksitler.
7. Two plans that fit a row equally well: the app asks which one; it never guesses.

**Swagger** (Register and **Authorize** as in 3.2.2): `PUT /api/v1/transactions/{id}/installment-plan` with `{"count": 6}`, `PATCH /api/v1/installment-plans/{id}` with `{"status": "CANCELLED"}`, `GET /api/v1/installments/schedule?from=2026-11-01&to=2027-06-01`. The stored candidates with their features are in `match_decisions` where `match_type = 'INSTALLMENT'`.

### 3.2.9 Try the home screen, analytics and budgets (P11)

No new migration. Rebuild the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`) and the app (3.3).

**The rules.** Spending = your purchases in the month you bought them, minus refunds (a refund is taken off the month of the purchase it refunds). An installment purchase counts once, with its full total, in its purchase month. Installment payments are never spending: they are only in **Bu ay ödenecekler**.

**A ready-made demo month (optional, development only).** Register a throw-away account whose e-mail ends with `@example.com` (in the app or in Swagger), then from `backend/`: `uv run python -m scripts.seed_demo --email <that e-mail>`. It refuses any other address and any account that already has purchases. Log in with that account: the home screen shows the numbers of the Figma frame.

**On the emulator or a phone**
1. **Ana Sayfa**, from top to bottom: the month (tap it to pick another month), the dark card with this month's spending and the change against the month before, **Kategoriler** (tap **Tümü** for all), **Dikkat gerektirenler** (budgets at 80 % or more), **Bu ay ödenecekler** (the installments due this month and six bars for the coming months).
2. Check one month by hand: open **Harcamalar**, filter the month with **Tarih**, add up the purchases yourself and compare with the home total (refunds arrive in P12; installment payments must not be added).
3. **Bütçeler** (Harcamalar → the chart icon → Bütçeler): set a limit for Market a little above what you spent this month, then add a Market purchase so that you pass 80 %: the home screen lists "Market bütçesi" in orange; above 100 % it is red.
4. **Analiz** (Harcamalar → the chart icon): Hafta / Ay / Yıl, the change against the period before with the categories that changed most, the ten places you spent most. With AI consent a one- or two-sentence comment may appear; it is written only from these numbers and disappears if the AI fails.

**Swagger**: `GET /api/v1/analytics/home?month=2026-11`, `/analytics/spending?from=2026-11-01&to=2026-11-30&group_by=merchant`, `/analytics/compare?...`, `/analytics/year?year=2026`, `PUT /api/v1/budgets` with `{"category_key": "GROCERY", "monthly_limit_minor": 600000}`. The budget reminders are in the table `reminders` (types BUDGET_80 / BUDGET_100, one each per category per month).

### 3.2.10 Try products, warranties, returns and refunds (P12)

New migration **0006** (the "do not ask again" answers and an index on refunds). Rebuild and migrate the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec -T backend alembic upgrade head`) and the app (3.3).

**The rules.** A purchase from 1.000 TL in Teknoloji, Ev & Yaşam or Giyim is offered as a product. Dates are suggestions with a visible source, never silent facts: the warranty is the purchase date + 2 years with the label "Yasal asgari süre (2 yıl)" and stays **ONAYLANMADI** until you accept or change it; the return window is purchase + 14 days only when bought **Online** ("Mesafeli satışta cayma hakkı"); for **Mağazada** there is no default and the app asks for the store's return period. A refund (full or part) lowers the spending of the month of the **original** purchase by the refunded amount only. A refund of the whole remaining amount, or "İade Edildi" on a product, marks the product **İade edildi**, closes its return window and deletes its pending reminders.

**Demo data (optional, development only).** `uv run python -m scripts.seed_demo --email <a throw-away @example.com account>` now also adds three products: a TV whose return ends in **2 days**, AirPods whose warranty ends in **20 days**, and a laptop bought in installments.

**On the emulator or a phone**
1. Share or scan a receipt of a technology item from 1.000 TL (or **+ → Manuel Harcama**, Giyim, 1.200 TL). After **Kaydet**: "Bunu ürün olarak takip edelim mi?" → **Evet** opens the product: GARANTİ with ONAYLANMADI and the 2-year label; İADE 14 days for Online, "Mağazanın iade süresini gir" for Mağazada. **Hayır, bir daha sorma** never asks for that purchase again.
2. **Ürünler**: "Teknoloji Kasam" (technology products, the warranty that ends first on top), the other products, filters Aktif / İade edildi / Arşiv, **+** for a product by hand.
3. Partial refund: open the purchase in **Harcamalar → İade ve ürün → İade edildi → Bir kısmı**, enter an amount. The list shows the net amount with "İade: -X TL"; the home total drops by exactly that amount in the purchase's month.
4. Full refund: on the product **İade Edildi → Tamamı**: the product shows İADE EDİLDİ and the return window "İade edildi"; it leaves "Dikkat gerektirenler".
5. Bank refund: share a card-list screenshot with a **+** (credit) row of a shop you bought from in the last 60 days. Under **Olası iadeler** the row says "X alışverişinin iadesi olabilir"; **İade olarak bağla** asks which purchase. Nothing is linked without your answer.
6. **Ana Sayfa → Dikkat gerektirenler**: returns ending within 7 days (İADE) and warranties ending within 30 days (GARANTİ) with the days left, then the budgets.

**Swagger**: `GET/POST /api/v1/products`, `GET /products/suggestions`, `POST /products/suggestions/dismiss`, `GET/PATCH/DELETE /products/{id}`, `PUT /products/{id}/warranty`, `PUT /products/{id}/return-window`, `POST /transactions/{id}/refund` with `{"amount_minor": 100000, "date": "2026-11-25"}`, `GET /refunds/suggestions`, `POST /observations/{id}/link-refund`.

### 3.2.11 Try reminders and notifications (P13)

New migration **0007** (a reminder can exist only once). Rebuild and migrate the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec -T backend alembic upgrade head`) and the app (3.3).

**The rules.** Warranty: 30 and 7 days before the end. Return: 3 days and 1 day before the last day. Last installment: on the 1st of the month it is due. All at **10:00 Istanbul time**. Budgets: at once, when 80 % / 100 % is reached. A reminder whose time has already passed when the date is set is not sent late (the home "Dikkat gerektirenler" shows it). A returned, archived or deleted product, a cancelled plan or a deleted purchase loses its reminders. Notifications are local: the phone schedules them from `GET /reminders/upcoming` (no server push).

**On the emulator or a phone (Android 13+)**
1. Sign in: the screen **"Son günleri kaçırma"** explains the notifications; **Bildirimlere izin ver** opens the system dialog (Allow). **Şimdi değil** never asks again from there; Settings can.
2. With the demo seed (3.2.9, 3.2.10) the Market budget is at 90 %: right after allowing, **"Market bütçenin %80'ine ulaştın."** appears. Tap it: **Bütçeler** opens.
3. **Ayarlar → BİLDİRİMLER**: one switch per kind (Garanti, İade, Taksit, Bütçe; stored on the phone), **Tam zamanlı bildirimler** (Açık / Kapalı; "Aç" opens the system page), and in debug builds **"Geliştirici: 2 dakika sonra bildir"** with one button per kind. Tap the four, wait 2–3 minutes (without exact alarms Android may delay a little), tap each notification: Garanti / İade → the product, Taksit → Taksitler, Bütçe → Bütçeler.
4. Change a product's warranty end (product → Tarihi değiştir): the reminders move at once. Mark a product **İade Edildi**: its reminders disappear.
5. Leave and reopen the app several times: no notification appears twice.

**To see what is scheduled** (debug build, emulator): `adb shell run-as com.receiptbox.receiptbox cat shared_prefs/scheduled_notifications.xml` lists every pending notification with its time and text; `adb shell dumpsys alarm | findstr receiptbox` shows the system alarms.

**Swagger**: `GET /api/v1/reminders/upcoming?days=60`, `POST /api/v1/reminders/{id}/dismiss`.

### 3.2.12 Try the AI assistant (P14)

New migration **0008**. Rebuild and migrate the backend (`docker compose -f infra/docker-compose.yml up -d --build backend`, then `docker compose -f infra/docker-compose.yml exec -T backend alembic upgrade head`) and the app (3.3). The assistant needs `GEMINI_API_KEY` and the AI consent. **Model**: `gemini-3.5-flash-lite` by default (DECISIONS D-015); `gemini-3.5-flash` allows only 20 requests a day on the free tier (2-3 per question). Leave `AI_MODEL_ASSISTANT` empty in your `.env` to use the default.

**What it does.** Turkish questions about your own records. The model may only call 8 typed tools (purchases, totals, comparisons, products, a product's card, deadlines, installments, documents); your user id is never one of their arguments. Every number in the answer must appear in this turn's tool results, otherwise the answer is corrected once or replaced by a templated one. The buttons under an answer open the screen where you can check each number.

**On the emulator or a phone** (demo seed, 3.2.9 / 3.2.10):
1. **Asistan** tab. Without the AI consent it says why and offers **Ayarlar'a git**; switch on "Yapay zekâ ile fiş okuma" and come back.
2. Tap the five suggestions one by one (**Geçmişi temizle** brings them back). Expected with the demo month: Market this month **5.420,00 TL**; AirPods warranty **16 Aralık, 20 gün**; remaining installments = **Taksitler → Kalan taksit toplamı**; the five most expensive purchases; "Kulaklığın faturası" finds AirPods' invoice (upload one first: product → Belgeler).
3. Tap each button under the answers and compare: Harcamalar opens with the filters set (the header shows the count and the total), the product card, the document, Taksitler.
4. Ask your own: something with no data ("Geçen ay sağlığa ne harcadım?" → "Kayıtlarında bununla ilgili bilgi bulamadım."), last year, a comparison ("Bu ay geçen aya göre daha mı çok harcadım?" → the home card's %8,8 / 1.520 TL), one shop.
5. Turn off the Wi-Fi of the emulator or stop the backend and ask: the red message with **Tekrar dene**.

**Swagger**: `POST /api/v1/assistant/chat` `{"message": "...", "history": []}` returns `answer`, `actions` and `tool_calls` (names and arguments); `DELETE /api/v1/assistant/history`. Every turn is in the table `assistant_turns` (outcome, latency, model, prompt version).

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
