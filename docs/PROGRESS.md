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
| P05 | AI provider layer & receipt extraction | ✅ Done | 2026-11-19 |
| P06 | e-Invoice QR, merchant normalisation, categorisation | ✅ Done | 2026-11-19 |
| P07 | Receipt review flow, manual entry, documents | ✅ Done | 2026-11-19 |
| P08 | Bank screenshot import | ✅ Done | 2026-11-22 |
| P09 | Matching engine 1:1 | ✅ Done | 2026-11-23 |
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

### 2026-11-23 — P09 follow-up: the receipt picture follows the receipt
- P09 CI on `main` was green (`6719f92`, `733e7b5`, `b8f3f8f`); P09 stays ✅.
- Done: after **Geri al** or **Ayır** the receipt / invoice picture now moves to the purchase of the receipt (`DocumentRepository.move_record_pictures`, called from `MatchService.unmerge`; rule and limits in DECISIONS P-071). Removed from the known gaps of P09.
- Tests added: backend **+4** (`tests/api/test_matches.py`): picture goes with the receipt after Geri al; stays with the receipt when the bank row is separated; follows the receipt when the receipt was the first record; other documents (warranty) stay. `ruff` clean.

### 2026-11-22 — P09 CI confirmed
- CI run on `main` (`6719f92`): jobs `backend` (1147 tests on a fresh PostgreSQL, fake provider only) and `mobile` (575 Flutter tests) both green. The emulator end-to-end run was done on 2026-11-23 (see the entry below), so P09 is closed. CI on `main` (`733e7b5`, the commit that records the emulator run): `backend` and `mobile` green again.

### 2026-11-22 — P09 Matching engine 1:1 (done; emulator end-to-end run on 2026-11-23)
- Done:
  - **The scorer is pure** (`backend/app/matching/features.py`): amount (50, linear to 0 at a 2 % relative difference), date (20 / 12 / 5), merchant (20 x similarity, alias hit = 1.0, else `token_set_ratio`), time (10, 5 minutes full, 0 at 60), missing features renormalised (`score = earned / available_max x 100`). Symmetric, so the order of arrival never changes a score. `MatchFeatures.as_json()` is stored as `match_decisions.features_json`; its 17 keys are documented in the module docstring and versioned (`baseline-v1`) because P15 trains a logistic regression on exactly them (`merchant_token_sort_ratio` is stored but not scored, to measure the "KAHVE" / "KAHVE DUNYASI" subset problem).
  - **Candidates** (`candidates.py`): same user, not deleted, PURCHASE, at most 3 days and 2 % away, and **no confirmed observation of the same source** (this is why two identical coffees from the bank stay two purchases).
  - **Decision** (`engine.py`, pure): one candidate >= `MATCH_SUGGEST` that also reaches `MATCH_AUTO` -> merge with undo; otherwise (also with several strong candidates) -> a suggestion and **no purchase is created until the user answers**; else a new purchase. The thresholds are settings (`MATCH_AUTO=95`, `MATCH_SUGGEST=70`, `MATCH_RECORD_MIN=50`, validated to be ordered, in `.env.example`), a test proves the same pair is merged, asked or ignored depending only on them. Every candidate >= 50 is stored in `match_decisions` with its features (chosen one AUTO_ACCEPTED / PENDING, the others REJECTED = "not this one", a negative example for P15). **Installment rows** (`k/n` marker, or `installment_count > 1`) are deferred before any scoring: `engine.defers_to_installments` is the hook for P10 (tested).
  - **Merge and unmerge** (`match_service.py`, `merge.py`): QR > receipt > bank > manual wins the merchant, category, date, time and total (a lower source stays evidence; the bank amount is kept on the observation). `match_decisions.merge_snapshot` (migration 0005, kept apart from `features_json`) holds the purchase before, the incoming record and the result, so "Ayır" gives back exactly two purchases, field by field and without undoing what the user edited after the merge; the decision becomes `UNDONE`.
  - **Where it runs**: receipt / QR confirm, bank rows (`confirm-batch`: `created` / `merged` / `suggested`), manual entries, and a **read-only preview** on every bank row of the import review (`match`: AUTO or SUGGEST; nothing is stored for a preview).
  - **API**: `GET /matches?decision=PENDING`, `POST /matches/{id}/accept`, `POST /matches/{id}/reject` (creates the purchase from what the user reviewed), `POST /transactions/{id}/unmerge`. `confirm` and `POST /transactions` answer 201 with `outcome` CREATED / MERGED (+ `match`) or **202** `{outcome: SUGGESTED, matches}`. New error codes `MATCH_NOT_PENDING`, `MATCH_NOT_AVAILABLE`, `NOT_MERGED`. Every endpoint is user-scoped (404 for another user's decision, purchase or observation).
  - **Mobile**: the question sheet ("Bu işlem daha önce eklediğin Migros fişiyle aynı olabilir. Birleştirilsin mi?", the two records side by side; several candidates = one "Bununla birleştir" each), the **Geri al** snackbar after an automatic merge (receipt, bank import, manual entry; it outlives the screen), "Eşleşti" / "Olası eşleşme" badges and a hint line on the bank import rows, **Ayır** per record in the purchase detail ("Birleşmiş kayıtlar"), and a banner "N eşleşme önerisi bekliyor" on Harcamalar for questions that were closed unanswered. There is no Figma frame for these: they use the existing tokens (`MatchBadge` is built like `ReviewBadge`; the "EŞLEŞTİ" badge the brief mentioned did not exist in the code).
- Tests added: backend **1147** (was 1033): 51 feature tests, 21 decision tests, 21 engine scenarios (the anonymised P08 bank fixtures with synthetic receipts that correspond to some of their rows: ±1 day, missing time, different spellings; negatives: identical coffees, same amount at another merchant, 4 days apart, 3 % apart in amount, another user's purchase, same source twice, installment rows, order independence, precedence QR > receipt > bank > manual, unmerge, thresholds from the settings, the preview), 21 API tests (accept, reject, conflicts, deleted purchase, isolation); Flutter **575** (was 543). FakeProvider only.
- Checks run on 2026-11-22: `ruff check`, `ruff format --check`, `pytest` (1147 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (575 passed).
- **Finding for P15 (measured by the unit tests, not an estimate).** With the spec 7.3 weights, amount + date alone are 70 of the 90 available points when the bank row has no time, so a **same amount, same day, unrelated merchant** pair scores **85.19**: inside the suggestion band, never automatic. The user answers "Ayrı kalsın" and that answer is stored as a REJECTED decision, i.e. exactly the negative example the logistic regression needs. If the evaluation shows too many such questions, a merchant gate (for example no suggestion below a minimum merchant similarity) is the first thing to try; it is not in the spec and was not added.
- Manual test steps for the owner: README §3.2.7.
- **Checked on the emulator on 2026-11-23** (debug build with migration 0005, real backend, real Gemini; the emulator had hung, the owner asked me to restart it; synthetic card lists drawn for the run and the synthetic receipts `receipt_market.jpg` and `receipt_a101_indirim.jpg`, a throw-away test account that was deleted afterwards): (1) a card list with four rows saved: **two identical coffees stayed two purchases** (4 purchases, 545,30 TL); (2) the market receipt for the 270,30 TL row, bank row first: **"Bu fiş mevcut bir harcamayla eşleşti ve birleştirildi." with Geri al**, still 4 purchases and the same 545,30 TL, the merged purchase showed the receipt's merchant and category; (3) **Geri al** → "Birleştirme geri alındı.", 5 purchases, 815,60 TL (the two); (4) the A101 receipt first, then a bank row one day later: the review showed **"Olası eşleşme"** and "Kaydedince sorulacak …", saving opened **"Aynı harcama olabilir mi?"** with the two records side by side, **Birleştir** → one purchase (total unchanged by the bank row), the detail listed **Birleşmiş kayıtlar** (Fiş 344,35 and Banka 344,35, each with **Ayır**); (5) **Ayır** on the bank record → "Kayıtlar ayrıldı: iki ayrı harcama var.", the detail kept only Fiş, a separate bank purchase appeared (9 purchases, 1.696,30 TL); (6) a bank row two days after the receipt, sheet closed without answering → purchase list banner **"1 eşleşme önerisi bekliyor"** (the waiting row is not counted), tapped → same sheet → **Ayrı kalsın** → "Ayrı bir harcama olarak kaydedildi."; (7) a bank row on the receipt's own date arriving after it: the review showed the green **"Eşleşti"** badge ("Mevcut harcamayla birleşecek"), saving said "2 harcama kaydedildi, 1 satır mevcut harcamayla birleşti." with **Geri al**, the total counted the A101 purchase once (2.445,65 TL) and Geri al brought the separate purchase back (14 purchases, 2.790,00 TL). Not seen on the emulator: a manual entry matching a bank row (widget tests only), the question for a receipt (the receipt review), and **no real phone**.
  - Seen there: a one-row card list gave OCR garbage (the same list with three rows was read perfectly), unrelated to matching; the receipt picture stayed on the first purchase after "Geri al" (fixed afterwards, see the follow-up entry above); a bank row identical (merchant, amount, date) to an earlier one is a P08 duplicate and gets no match preview.
- Known gaps / follow-ups:
  - The receipt image is uploaded to the purchase the receipt was merged into; after "Geri al" / "Ayır" it now moves with the receipt (P09 follow-up, no longer a gap). A question left unanswered deletes the kept image (the receipt itself stays pending and can still be answered from Harcamalar).
  - Unmerge is for 1:1 merges (exactly two records). Installment purchases with several payments are P10.
  - Merging is by the single best candidate rule of spec 7.4; the user is asked for one waiting record at a time.
  - A merged purchase keeps its payment type and note; only merchant, category, date, time, total and (when known) channel come from the higher source.

### 2026-11-22 — P08 CI confirmed
- CI run on `main` (`68b71e9`): jobs `backend` (1033 tests on a fresh PostgreSQL, fake provider only) and `mobile` (543 Flutter tests) both green. P08 is closed.

### 2026-11-22 — P08 Bank screenshot import (done locally; CI confirmed in the entry above)
- Done:
  - **Decisions** (D-013, D-014; implementation choices P-061…P-064 in DECISIONS.md): supported banks **Garanti BBVA** (folders `garanti` + `bonus`, Bonus is Garanti's card brand), **Kuveyt Türk**, **Akbank**, each with its own prompt hints (`prompts/banks/*.md`); **QNB and Ziraat** have no hints and are the held-out "unseen bank" set (kept for P15 evaluation E1). POS slips are one row; current-account screens are refused; card-bill payments are "Kart ödemesi" and never saved; refunds stay observations "possible refund" (P12); loyalty-point and 0,00 TL rows are dropped.
  - **On-device privacy first**: a check of the real screenshots found 7 kinds of leaks in the masked text (balance and statement lines, account numbers, transfer parties, first card digits, slip name lines, an OCR spelling of "Bakiye"); `PiiMasker.mask(bank: true)` now covers all of them (only the kinds were reported, never the values). The bank screenshot image never leaves the phone and is never kept (a test checks the source for upload and retained-image code).
  - **Backend**: `POST /extract/bank-screenshot` {masked_text, bank_hint?, capture_date} → screen check (account screens: `BANK_SCREEN_NOT_SUPPORTED`) → `AIProvider.extract_bank_rows` (Gemini + Fake) with `bank_rows.v1.md` + the bank's hints → **deterministic validation** (`ai/bank_validation.py`: the amount must be printed in the text and in TL, the sign gives the direction, Akbank's inverted sign, payments set aside, refunds flagged, headers/totals/points/zero dropped, a date the model made up is dropped because it must appear in the text) → `date_resolver.py` (Bugün/Dün/weekday/`12 Kasım`/`12.11`/`12/11/2026`, never in the future, 2 Jan + "30 Aralık" = previous year) → `installment_marker.py` (8+ variants) → merchant and category suggestions (no AI per row) → fingerprint (spec 7.2; identical rows in one screenshot get an occurrence number) → `BANK_SCREENSHOT` observations `PENDING_REVIEW` or `DUPLICATE`. `POST /observations/confirm-batch` {ids, edits} creates purchases for the selected debit rows (credits stay observations). Masked text of the first stored row is nulled after 30 days at startup (`services/retention.py`). **The LLM computes nothing**: it copies text; amounts become kuruş in Python.
  - **Mobile**: keyword `BankDetector` (garanti / kuveyt / akbank; other banks mean no hint), **Banka ekran görüntüsü** screen: "Banka" chip to change the bank (re-reads the text), one card per row (merchant, date, amount, category, installment chip `1/3`, "KONTROL ET" on weak fields, "Tarih okunamadı" blocks saving until a date is typed), select / deselect all, edit sheet, sections "Olası iadeler", "Daha önce eklenmiş", "Atlanan satırlar", "Seçilenleri Kaydet". Bank screenshots no longer open the P04 debug panel (still reachable by the debug link).
  - **Manual real-model run** (`ai/experiments/run_bank_extract_manual.py`; masked text only; reads the git-ignored `ai/datasets/bank_masked` and `bank_expected`).
- Tests added: backend **1033** (was 764): date resolver, installment markers, validation, 19 sanitized fixture sets (only masked or synthetic text, same layouts), provider and retention, API (extract, duplicates, confirm-batch, cross-user 404); Flutter **543** (was 467): detector, models, import screen (rows, refunds, duplicates, skipped, bank change, edit, save, errors, no upload of the image), masker bank rules. FakeProvider only.
- Checks run on 2026-11-22: `ruff check`, `ruff format --check`, `pytest` (1033 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (543 passed).
- **Accuracy with the real model** (`gemini-3.5-flash-lite`, end to end: the owner's masked OCR text, OCR mistakes count as mistakes, 2026-11-22):

  | | screenshots exactly right | row recall | row precision | date ok | installment ok | payments/points imported |
  |---|---|---|---|---|---|---|
  | **Supported banks** (Garanti/Bonus, Kuveyt, Akbank; 16 screenshots) | 12/16 (75 %) | 52/55 (94.5 %) | 52/53 (98.1 %) | 50/52 | 50/52 | 0 |
  | **Unseen banks** (QNB, Ziraat; 2 screenshots, no hints) | 1/2 (one run: 0/2, the model is not deterministic) | 5/7 (71 %) | 5/5 (100 %) | 5/5 | 5/5 | 0 |

  Both account screens were refused. Misses: Akbank POS slips (date and installment garbled by OCR), one Akbank row cut off at the bottom, Kuveyt `1.605,o0` (letter o in the amount, dropped, shown under "Atlanan satırlar") and one amount OCR-read as `3.014,39` instead of `3.014,89`, QNB: one or two rows missing and merchant names garbled by OCR (`Asil Kart`, `Ek Kart- ka`). The small sample (18 screenshots from one person) means these percentages are only indicative; the real evaluation is P15.
- **Checked on the emulator** (debug build, real backend and real Gemini, all 19 of the owner's screenshots pushed to the emulator gallery and shared to the app; nothing uploaded except masked text): the bank was detected for Garanti/Bonus, Kuveyt and Akbank (QNB and Ziraat: "Diğer banka"); row counts, amounts, dates and installment chips were compared with each screenshot: Garanti/Bonus 04–11 all as expected (04 and 05 are account screens: "Bu ekran kart hareketi değil"; 09 has one possible refund), Kuveyt 12, 13, 14, 16, 17 as expected (refunds under "Olası iadeler"), Kuveyt 15 and Akbank 01, 02, 03 as in the list above, Ziraat 2/2, QNB 4/5. **Save**: screenshot 06 → "5 harcama kaydedildi." and the five purchases (2.878,57 TL together) are in Harcamalar. **Duplicate**: screenshot 07 (identical to 06) → all rows under "Daha önce eklenmiş (5)", none selectable. Found there and fixed: the text "Harcama satırı bulunamadı" was shown for a screenshot of only known rows (now "Yeni harcama yok"), the İptal button was full width (now a text button). The two fixes were covered by widget tests; **the final debug build with those two fixes was not reinstalled on the emulator**.
- Manual test steps for the owner: README §3.2.6.
- Known gaps / follow-ups:
  - **Real phone not tried** (emulator only). Owner check: import 3 real screenshots from each bank and compare with the bank app.
  - OCR mistakes reach the user as wrong digits or dropped rows (the amount must be printed in the text, so a letter in an amount drops the row instead of guessing): the user sees them in "Atlanan satırlar" or fixes them in the edit sheet. Akbank POS slips usually come without date and installment ("Tarih okunamadı" until the user types one).
  - Model choice: tests ran on `gemini-3.5-flash-lite` (the default of `AI_MODEL_EXTRACT`). A larger model reads the Garanti lists more reliably (list misalignment seen with flash-lite); the owner can switch with the environment variable and rerun the manual script, quota allowing.
  - Every bank row gets the category "Diğer" for now (no AI per row; merchants not in the seed list have no default); the user can set it in the edit sheet. Matching with receipts is P09, installments P10, refunds P12.
  - The 19 fixture sets are built from masked texts (names, amounts and dates changed by a sanitizer) and synthetic text in the same layouts. `qnb_1` and `ziraat_1` are such sanitized copies, used only to check that these banks are read **without** a hint; the unchanged masked texts stay git-ignored (`ai/datasets/`) and are reserved for the P15 evaluation.

### 2026-11-19 — P07 CI confirmed
- CI run on `main` (`67bf62c`): jobs `backend` (764 tests on a fresh PostgreSQL, fake provider only) and `mobile` (467 Flutter tests) both green. P07 and Milestone M1 are closed.

### 2026-11-19 — P07 Receipt review flow, manual entry, documents (Milestone M1; done locally, CI confirmed in the entry above)
- Done:
  - **Backend**
    - `POST /observations/{id}/confirm` (edited merchant, date, time, total, category, channel, note, items, `remember_category_for_merchant`): creates a NEW `PURCHASE` transaction, links the observation as `CONFIRMED`, saves a user category rule when asked. `installment_count > 1` only sets `payment_type = INSTALLMENT` (P10 does the rest). **No matching** (P09). `POST /observations/{id}/reject`, `GET /observations?status=PENDING_REVIEW`.
    - Transactions: `GET /transactions` (date range, category, merchant, text search, limit/offset; answers also `count` and the net `sum_minor` of everything that matches), `GET /transactions/{id}` (evidence + items in receipt order + documents), `PATCH`, soft `DELETE` (also deletes its documents), `POST /transactions` (manual: a `MANUAL` observation + the transaction). Money is `*_minor` integers in these APIs.
    - Documents: `StorageBackend` + `LocalStorage` (`STORAGE_ROOT/users/<user_id>/<uuid>`), `POST /documents` (multipart; type found from the file's first bytes, jpeg/png/pdf only, 10 MB, sha256), `POST /documents/{id}/access-token` (5 minutes, bound to document and user, a different token type from the login token), `GET /documents/{id}/content?token=`, `DELETE`. Deleting the account also deletes the files.
    - Migration `0004`: `receipt_items.position` (items were returned in random order).
  - **Mobile**
    - **Review screen** (Figma "02 · Fiş Kontrol"): custom app bar, receipt card, banner ("N alan kontrol bekliyor" / all verified), the fields card (merchant, date + time, total, category sheet with 13 options, "Nereden alındı?" segmented control), green check on verified fields, "KONTROL ET" badge and warm background on MEDIUM/LOW ones (editing a field clears its flag), collapsible items card with editing and the "do the items add up to the total" line (same tolerance as the server), "Vazgeç" / "Kaydet".
    - Reading state (up to a minute, can be cancelled). If the receipt cannot be read (`EXTRACTION_FAILED`, `EXTRACTION_REJECTED`, `QR_INVALID`, no network, AI reading switched off) the same form opens empty with a notice and is saved as a manual purchase (the picture is still kept).
    - "Bu mağaza için hep böyle olsun mu?" is asked **before** the confirm request when the category was changed; the answer travels with it.
    - "Fiş görsellerini sakla" now works: the capture pipeline keeps a privacy-cleaned JPEG (upright, at most 2000 px, no EXIF/GPS) or the original PDF in the temporary folder; after the purchase is saved it is uploaded (one retry) and deleted. A failed upload keeps the purchase and says so. **A bank screenshot is never kept** (a pipeline rule, tested).
    - **Vazgeç / back** asks, rejects the observation on the server and deletes the kept picture.
    - **Harcamalar**: list grouped by day, category filter, date-range filter, search, count and total of the filtered result, pull to refresh, "Daha fazla göster". **Detail**: amount, category, evidence chips (Fiş / e-Fatura / Banka / Manuel), items, stored picture or PDF first page loaded with an access token, full-screen viewer with zoom, edit (same form as manual entry), delete with confirmation. **Manuel Harcama** form (merchant, amount, date, time, category, channel, note); also opened by the "+" in the list header.
    - Bank screenshots still open the P04 "Okunan bilgiler" screen (P08); a debug link on the review screen opens it for receipts too.
- Tests added: backend **764** (was 636): documents (upload types and size, hash, token expiry, token for another document or user, deleting), observations (confirm / reject / list, rule, installment flag, double confirm, validation), transactions (filters, search, pagination, soft delete, manual, patch), cross-user isolation (404) for **every** new endpoint, migration, account deletion; Flutter **467** (was 382): review form and flags, money parsing, review screen (badges, banner count, editing clears flags, sum check, "hep böyle" dialog, save, errors, Vazgeç, manual fallback for each error), review controller with real files (upload, retry, deletion), pipeline keeping rules, list / detail / manual screens. FakeProvider only, no real AI call in any test.
- Checks run on 2026-11-19: `ruff check`, `ruff format --check`, `pytest` (764 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (467 passed).
- **Checked on the emulator** (debug build, real backend with migration 0004, real Gemini, synthetic receipts): gallery market receipt → review (one field flagged, items add up) → category changed → "hep böyle" yes → saved → appears in Harcamalar with the paperclip → detail shows the picture; the **same receipt again** came back auto-categorised, all fields verified, green banner; shared `einvoice_qr.pdf` → "e-Fatura PDF" card, channel Online, saved with the e-Fatura chip, the PDF's first page shown and opened full screen; a failed reading (the machine briefly lost DNS) opened the manual form and saved with the picture; manual entry; Vazgeç rejected the observation on the server and left no file in the app's temporary folder. Found there and fixed: the text fields showed an inner border (the global input theme), the viewer's back arrow was invisible on black. **Not checked on the emulator**: editing and deleting a purchase (widget tests only), a PDF **with** several pages.
- Manual test steps for the owner: README §3.2.5.
- Known gaps / follow-ups:
  - **Real phone / camera not tried** (no phone was connected; the emulator camera is not a real receipt). Owner check: photograph 5 real receipts with "Fiş Tara", fix one wrong field each time and add up the list by hand.
  - No matching yet (P09): the same receipt added twice makes two purchases. The Home tab is still the P03 placeholder (P11).
  - `merchants` has no owner column, so a merchant created at confirm is global; its name is only reachable through the creating user's private alias, and the name shown on a purchase is the text the user confirmed (P-056). The seller tax number of a QR invoice is not saved as an alias (the number is not stored, P-047).
  - A receipt closed with the app killed mid-review stays `PENDING_REVIEW` on the server (listable with `GET /observations`); the temporary picture is cleared at the next start. Cancelling while the server is still reading leaves the same pending observation. A failed picture upload cannot be repeated later (no "add picture" screen yet).
  - Category colours are provisional (6 from the Figma palette plus 7 derived, P-059); the list, detail and manual screens have no Figma frames and were built from the same tokens and components (DESIGN_TRACK rows 2 and 9).
  - Sharing a file with a `file://` address from `/sdcard` (the adb way) is refused by Android; real shares use `content://` and work (P04). For the emulator check the PDF was shared from the app's own folder.

### 2026-11-19 — P06 CI confirmed
- CI run on `main` (`961b3f5`): jobs `backend` (636 tests, fake provider only) and `mobile` (382 Flutter tests) both green. P06 is closed.

### 2026-11-19 — P06 e-Invoice QR, merchant normalisation, categorisation (done locally; CI confirmed later the same day)
- Done:
  - **GİB QR (`backend/app/qr/gib_qr.py`)**: tolerant parser (case-insensitive keys, JSON object or text, amounts as numbers or text with dot or comma, several date formats, unknown keys ignored). `odenecek` is the total, `vergidahil` the fallback, `tarih` the date, `ettn` the `external_id`; the buyer's `avkntckn` is dropped again on the server; only whitelisted fields are saved, the seller's tax number is only used for a lookup. The phone keeps recognising the QR and removing the buyer's number (P04): nothing is duplicated (P-047).
  - **`POST /extract/einvoice-qr`** `{qr_payload, masked_text?, capture_date}`: observation `source=EINVOICE_QR`, QR fields HIGH, fingerprint from the ETTN. A QR-only invoice makes **no AI call** and needs no consent; with the invoice text and the consent the AI adds merchant name and items (the QR keeps total and date). Errors `QR_INVALID`, `EXTRACTION_REJECTED`, `TEXT_TOO_LARGE`; shares the 20/min limit (P-048).
  - **Merchant normaliser (`app/matching/merchant_normalizer.py`)**: spec 5.6 steps 1-5 as pure functions plus repository calls: cleaning (legal words, store numbers, trailing city, `.COM`), alias lookup (user before global, Turkish and ASCII spelling), rapidfuzz with a guard against subset matches, otherwise a NEW proposed name. No merchant row is created while reading a receipt (P-049, P-050).
  - **Categorisation**: user rule > merchant default > `classify_category` (Gemini enum answer / Fake) > OTHER (P-051). Marketplaces (default OTHER) ask the AI when there are items. A failure never fails an extraction.
  - **Both endpoints** store `extraction_json.suggestions` and return `suggestions {merchant, category}`.
  - **Mobile**: `ExtractionApi` picks `/extract/einvoice-qr` when the capture has a GİB QR, else `/extract/receipt` (only with the local AI consent); a debug-only "Sunucuya gönder (debug)" panel on the result screen shows the server's answer (P-052).
  - `ai/experiments/make_synthetic_samples.py` also makes `einvoice_qr.pdf`, a synthetic e-Archive invoice with a QR code (made-up buyer TCKN inside the QR and printed on the page).
- Tests added: backend **636** (was 438): `test_gib_qr.py` (58 cases: amounts, dates, malformed JSON, privacy), `test_merchant_normalizer.py` (85 cases, 40 real-looking names incl. all the phase's examples, user aliases, cross-user isolation), `test_categorization.py` (19: precedence, consent, failures), `tests/api/test_extract_einvoice.py` (QR-only = zero AI calls, consent, privacy of the buyer number, errors, limits, suggestions), Gemini classification tests; Flutter **382** (was 355): endpoint choice, consent, error messages, the debug panel; the privacy guard now allows one explicit network file. FakeProvider only, no real AI call in any test.
- Checks run on 2026-11-19: `ruff check`, `ruff format --check`, `pytest` (636 passed, Docker database running), `flutter analyze` (no issues), `flutter test` (382 passed).
- **Checked on the emulator** (debug build, real backend, real Gemini, synthetic invoice): sharing `einvoice_qr.pdf` found the QR on the phone ("e-Fatura QR kodu bulundu"), hid the name and the T.C. kimlik no, and "Sunucuya gönder" returned total 2499.00, date 2026-11-14, a TECHNOLOGY category chosen by the AI and the confidence per field. Two bugs found there and fixed: ML Kit read "İ" as "Ỉ" (the merchant name was not cleaned), and invoice lines add up to the amount before tax, so the items were rated LOW against the amount to pay.
- Manual test steps for the owner: README §3.2.4 (Swagger and emulator).
- **Seed review for the owner (O-004 in DECISIONS)**: nothing in `merchants_seed.csv` was changed. Risky categories: Decathlon (CLOTHING), books (EDUCATION vs D&R ENTERTAINMENT), pay-TV (BILLS vs streaming SUBSCRIPTION), Arçelik HOME vs other electronics TECHNOLOGY, Tchibo, App Store / Google Play. Risky aliases: `PARIBU` (a crypto exchange too), generic words `TOTAL`, `NERO`, `DAMAT`, `VATAN`, `MARTI`, `GAIN`, `FLO`, `MAVI`, `PEGEM`, `VALVE`, very short ones (`BP`, `LG`, `HM`, `HGS`...). Missing: Beko, pharmacies, cargo companies, classified sites, most utilities.
- Known gaps / follow-ups:
  - **No real e-Archive QR was tried**; only synthetic payloads. The real GİB QR layouts (field names, number and date formats) may differ per software vendor: bring a real one (owner check below) and add it to the tests.
  - The QR holds no merchant name: a QR-only invoice has merchant `LOW` and no category (OTHER, FALLBACK) until the text is read by the AI (consent) or the user names the shop in P07. Seller tax number -> merchant aliases (`VKN ...`) are looked up but nothing creates them yet (P07).
  - A NEW merchant is only a proposed name; P07 must create it when the user confirms (`MerchantRepository.create`) and show the "Bu mağaza için hep böyle olsun mu?" question that stores a user rule (`set_user_rule` exists, no UI).
  - Fuzzy matching and the generic-word risk: names that are a common word can match by exact alias (seed review). OCR spelling variants other than "Ỉ" may exist.
  - The category AI call adds a second AI call (about 2-10 s) for unknown merchants; the review screen must tolerate about 30-40 s in total.
  - The debug panel's AI-consent check uses the local switch only.
  - ~~CI for this phase has not run yet~~ → green on 2026-11-19, see the entry above.
- Manual check for the owner: scan the QR of a real e-Archive invoice from an online order (share the PDF to the app, press "Sunucuya gönder (debug)") and confirm date and total are exact.

### 2026-11-19 — P05 CI confirmed
- CI run on `main` (`d5d00a6`): jobs `backend` (438 tests on a fresh PostgreSQL, no API key, fake provider only) and `mobile` (355 Flutter tests) both green. P05 is closed.

### 2026-11-19 — P05 AI provider layer & receipt extraction (done locally; CI confirmed later the same day)
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
  - ~~CI for this phase has not run yet~~ → green on 2026-11-19, see the entry above.

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
