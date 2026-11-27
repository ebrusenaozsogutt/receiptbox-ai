# P15 — Evaluation Harness & Experiments

**Goal:** Reproducible experiments E1–E4 producing the tables and figures for the report. All numbers come from real runs.
**Depends on:** P14 (and labelled data collected since week 2) · **Week:** 13
**Read first:** spec §19 (entire)

## Scope

1. `ai/experiments/` Python package (separate `pyproject.toml`, may import `backend/app` modules). Config via YAML; results written to `ai/experiments/results/<exp>/<timestamp>/` (CSV + JSON + PNG). Datasets read from git-ignored `ai/datasets/`.
2. **Labelling tool:** `label_receipts.py` — loads masked OCR texts exported from the app (debug export) and lets the owner write/correct gold JSON quickly (CLI or simple Streamlit-free TUI; plain JSON files are fine).
3. **E1 Extraction:** systems S1 (regex rules baseline, implemented here), S2 (LLM), S3 (LLM + validation), S4 (QR-first + S3), S5 (image → multimodal LLM, images loaded locally only for this experiment). Merchant-disjoint split. Metrics: field exact match (merchant normalised, date, total), item P/R/F1 (fuzzy ≥ 85 + exact price), category accuracy, latency, tokens. Bootstrap 95% CIs.
4. **E2 Matching:** build labelled pairs (`same`, `installment`, `unrelated`) from real receipts + bank rows + synthetic rows (`synth_bank_rows.py`). Compare deterministic scorer vs logistic regression (scikit-learn, 5-fold CV) on identical features. Metrics: P/R/F1, PR curves, chosen thresholds; 1:1 and 1:N reported separately.
5. **E3 Assistant:** `assistant_benchmark.yaml` with 60–100 Turkish questions over a seeded demo DB; gold answers computed by SQL; metrics: tool-selection accuracy, numeric correctness, hallucination rate, correct no-data responses, latency.
6. **E4 Privacy:** synthetic texts with injected PII (generator) → masking recall / false-positive rate (Dart masker run via a small CLI or ported test vectors).
7. `make_report_assets.py` → Markdown tables + figures into `docs/report_assets/`.
8. Free-tier handling: request pacing to stay under rate limits; caching of LLM responses per (system, input hash) so reruns are free.

## Out of scope

Hyper-parameter sweeps beyond thresholds, training any OCR/LLM model.

## Acceptance criteria

- [x] One command per experiment reproduces results from cached responses. *(E3 replays from `ai/experiments/cache/e3/`; E4 is seeded; E1 / E2 the same once data exists.)*
- [ ] E1 run on ≥ 150 labelled receipts (or all available, stated in the report).
- [ ] E2 PR curve and threshold table produced; chosen thresholds written back to backend config with justification in DECISIONS.
- [ ] E3 run on ≥ 60 questions; E4 on ≥ 500 synthetic samples.
- [ ] `docs/report_assets/` contains all tables/figures with captions.

## Tests

Unit tests for metric functions (exact match, item F1, PR computation) in `ai/experiments/tests/`.

## Manual check for the owner

Read the result tables; spot-check 10 E1 errors and 10 E2 errors and write short error-analysis notes (needed for the report).
