# ReceiptBox AI evaluation harness (P15, spec 19)

Gemini **free tier only** (D-016). Every real request passes the shared daily cap
(`AI_MAX_REQUESTS_PER_DAY`, counted in the `ai_daily_requests` table). The experiments stop
earlier, at `stop_at_requests` in their config, so the app keeps the rest of the day's requests.
Answers are cached per request (model, system prompt, input, tools), so a rerun is free and gives
the same numbers. Requests are paced under the per-minute limit. When the day's budget is used
up, a run stops and is simply started again the next day.

Setup (once): Docker Desktop running, the database migrated (`cd backend && uv run alembic
upgrade head`), then `cd ai/experiments && uv sync`.

| Experiment | Command (from `ai/experiments/`) | Data | Results |
|---|---|---|---|
| E4 privacy | `uv run python e4_privacy.py` | 600 seeded synthetic texts, the app's Dart masker (`mobile/tool/mask_jsonl.dart`) | `results/e4/<time>/` |
| E3 assistant | `uv run python e3_assistant.py` | `assistant_benchmark.yaml` (88 questions) on a rebuilt database `receiptbox_eval` | `results/e3/<time>/`, cache `cache/e3/` (committed) |
| E1 extraction | `uv run python e1_extraction.py` | your labelled receipts, `ai/datasets/receipts_real/` | `results/e1_receipts_real/<time>/`, cache `ai/datasets/_cache/e1/` (private) |
| E2 matching | `uv run python e2_matching.py` | your verified pairs, `ai/datasets/e2_pairs/real.jsonl` | `results/e2_real/<time>/` |
| Report | `uv run python make_report_assets.py` | the latest run of each experiment | `docs/report_assets/` |

`results/` is not committed: each experiment is one command from the same inputs. Unit tests:
`uv run pytest -q`; they also run in CI.

## Part B: your receipts (E1) and your bank rows (E2)

1. Capture the receipts with the app (camera, gallery or share). Turn on "Fiş görsellerini sakla"
   if you want S5 (the photo goes to the model unmasked; you decide per receipt).
2. `uv run python export_receipts.py --email <your e-mail> --images`. This writes the masked
   texts, the QR fields and your saved values (as an unverified pre-fill) to
   `ai/datasets/receipts_real/`. This folder never goes to git.
3. `uv run python label_receipts.py`. For each field: Enter confirms it, a new value corrects it,
   `-` means "not on the receipt", `?` skips it (it will not count), `q` saves and stops. The
   last question asks whether S5 may send this receipt's photo.
4. `uv run python e1_extraction.py`. S1-S5 on the test split (no shop is in both dev and test).
   With 150+ receipts the free tier needs several days: run the same command each day.
5. Bank screenshots of the same period imported in the app create the matching decisions.
   `uv run python export_pairs.py --email <your e-mail>`, then `uv run python label_pairs.py`
   to confirm each pair, then `uv run python e2_matching.py`.
6. `uv run python make_report_assets.py`.

Pipeline checks without real data (their numbers are not results):
`uv run python make_synthetic_e1.py`, then `uv run python e1_extraction.py --dataset
receipts_synthetic --provider fake --split all`; `uv run python synth_bank_rows.py`, then
`uv run python e2_matching.py --pairs synthetic`.
