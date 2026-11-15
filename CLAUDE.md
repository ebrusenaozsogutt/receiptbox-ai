# CLAUDE.md — ReceiptBox AI

You are implementing **ReceiptBox AI**, an Android purchase-memory app (Flutter + FastAPI + PostgreSQL) for a single-semester senior design project. The owner (Ebru) reviews and tests; you write the code.

## Read before any work

1. `.claude/skills/receiptbox-scope/SKILL.md` — scope, non-goals, invariants. **Load it every session.**
2. `docs/PROGRESS.md` — what is done, what is next.
3. The current phase file in `docs/phases/` — work on **one phase at a time**.
4. `docs/spec/00_PROJECT_SPEC.md` — read only the sections the phase file lists.

## Working loop (per phase)

1. Read the phase file completely. If something is ambiguous or conflicts with the spec, **stop and ask** (add it to `docs/DECISIONS.md` under "Open").
2. Write a short plan (files to create/change, tests to write) and show it to the owner before large changes.
3. Implement in small commits. Write tests alongside the code.
4. Run all checks (below). Fix failures before continuing.
5. Tick the phase's acceptance criteria, update `docs/PROGRESS.md` (date, what was done, known gaps), and explain to the owner in Turkish **what was built and how to test it manually** (the owner must be able to defend the code).
6. Do not start the next phase until the owner says so.

## Hard rules

- **Never implement anything outside the current phase or outside spec Section 3.1.** If you think something is missing, propose it; don't build it.
- **Money** is `int` minor units (kuruş) everywhere in code and DB. Never `float`.
- **Every** repository/service function touching user data takes `user_id` and filters by it.
- **The LLM never computes numbers.** Totals, comparisons, deadlines come from SQL/Python.
- **No provider SDK imports outside `backend/app/ai/providers/`.** Model names come from env vars.
- **No raw PII**: bank screenshot images never leave the device; OCR text is masked on device; never log OCR text, tokens, e-mails, or amounts together with merchant names.
- **Never commit** secrets, `.env`, real receipts, real bank screenshots, or anything under `ai/datasets/`.
- **Tests use `FakeProvider`**, never a real LLM. Real-LLM calls only in `ai/experiments/` and manual runs.
- UI strings are **Turkish**; code, identifiers, comments, docs are **English**.
- Prefer boring, explicit code over clever abstractions. No new dependency without a one-line justification in the PR/commit message.

## Commands

```bash
# infra
docker compose -f infra/docker-compose.yml up -d db

# backend (from backend/)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check .
uv run pytest -q

# mobile (from mobile/)
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
flutter run   # Android device/emulator; backend URL via --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Conventions

- Backend layering: `api/` (routers, no logic) → `services/` (logic) → `repositories/` (SQL). Pydantic schemas in `schemas/`, ORM models in `models/`.
- Errors: raise domain exceptions; a single handler maps them to `{"error": {"code", "message"}}`.
- Mobile: feature-first folders (`data/`, `domain/`, `presentation/`), Riverpod providers, go_router routes declared in `app.dart`.
- Dates: store `date`/`timestamptz`; business timezone `Europe/Istanbul`.
- Commit messages: `P07: add receipt review confirm endpoint`.

## Definition of done (every phase)

- All acceptance criteria in the phase file are checked.
- `ruff`, `pytest`, `flutter analyze`, `flutter test` pass; CI green.
- No TODOs left for in-scope items (out-of-scope notes go to `docs/DECISIONS.md`).
- `docs/PROGRESS.md` updated.
