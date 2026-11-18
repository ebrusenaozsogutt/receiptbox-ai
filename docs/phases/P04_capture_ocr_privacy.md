# P04 — On-device Capture: OCR, QR, PII Masking, Share

**Goal:** From any image/PDF source, produce on the phone a `CapturePayload` = masked OCR text + optional GİB QR payload + metadata. Nothing is uploaded yet.
**Depends on:** P03 · **Week:** 3
**Read first:** spec §5.1, §5.5 (first two steps), §15.1, §15.3

## Scope

1. Sources: camera (`camera` package, simple capture screen with guide frame), gallery (`image_picker`), Android share sheet (`receive_sharing_intent`: images + PDF). PDF → first 2 pages rendered to images (`pdfx`).
2. Image preprocessing: downscale long edge to ≤ 2000 px, auto-rotate by EXIF. (No heavy CV.)
3. `core/ocr/qr_service.dart`: ML Kit barcode scanning; detect GİB QR (JSON containing keys like `ettn`, `odenecek` or `vergidahil`); **drop `avkntckn`** (buyer ID) before returning.
4. `core/ocr/ocr_service.dart`: ML Kit text recognition (Latin); return text lines in reading order with block structure preserved as `\n`.
5. `core/privacy/pii_masker.dart`: all rules in spec §15.1 (IBAN, Luhn card numbers incl. partially masked, TCKN checksum, phone, e-mail, balance/limit lines, name heuristics). Returns masked text + counts per type (counts only, for metrics).
6. `CapturePayload` model: `{kind: RECEIPT|BANK_SCREENSHOT, masked_text, qr_payload?, capture_date (device date; for screenshots use file last-modified if available), source: CAMERA|GALLERY|SHARE}`.
7. Debug screen (only in debug builds): shows original OCR text vs masked text side by side and QR result — for the owner to verify on real receipts.
8. User picks kind when ambiguous: camera → RECEIPT; gallery/share → ask "Fiş mi, banka ekran görüntüsü mü?".

## Out of scope

Uploading/extraction (P05/P08), storing images (P07).

## Acceptance criteria

- [x] Camera, gallery and share (from Gallery app and from a PDF viewer) all produce a `CapturePayload`. *(Emulator: gallery picker, share from the Files app and via share intents for an image and a PDF, camera via the emulator's virtual scene. The camera on a real phone is a manual test for later, see PROGRESS known gaps.)*
- [x] GİB QR detected on a sample e-Archive invoice; `avkntckn` absent from output. *(Synthetic invoice; real ML Kit on the emulator.)*
- [x] PII masker unit tests: ≥ 40 cases, 100% pass, including Turkish text around numbers and false-positive checks (e.g. receipt totals and dates are **not** masked; 11-digit numbers failing TCKN checksum are not masked).
- [x] Original (unmasked) text is never persisted or sent; verified by code review note in PROGRESS.
- [x] Works offline (no network needed for this phase). *(Integration test passes in airplane mode.)*

## Tests

`pii_masker_test.dart` (≥ 40 cases), `qr_parser_test.dart` (sample payload strings), widget test for kind picker.

## Manual check for the owner

Photograph 10 real receipts and 2 bank screenshots; open the debug screen; confirm masking hides IBAN/card/name/balance and keeps totals/dates readable.
