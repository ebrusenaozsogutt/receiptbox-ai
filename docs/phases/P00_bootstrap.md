# P00 — Repository Bootstrap & Tooling

**Goal:** A clean monorepo where the backend, mobile app, database and CI all start with one command each.
**Depends on:** nothing · **Week:** 1
**Read first:** spec §4, §18, §21 · `CLAUDE.md`

## Scope

1. Create the folder layout from spec §21 (empty `ai/experiments/`, `ai/datasets/` with `.gitkeep` and git-ignored contents).
2. Root `.gitignore` (Python, Flutter/Android, `.env`, `ai/datasets/*`, `backend/storage/`), `.editorconfig`, `README.md` (setup steps for Windows + Android).
3. `infra/docker-compose.yml`: `db` (postgres:16, volume, healthcheck) and `backend` (built from `backend/Dockerfile`, depends on db).
4. Backend skeleton (`backend/`): uv project, FastAPI app factory `app/main.py`, `app/core/config.py` (pydantic-settings: `DATABASE_URL`, `JWT_SECRET`, `STORAGE_ROOT`, `AI_PROVIDER`, `AI_MODEL_EXTRACT`, `AI_MODEL_ASSISTANT`, `GEMINI_API_KEY`), `GET /api/v1/health` returning `{status, db}`; async SQLAlchemy engine/session dependency; global error handler producing `{"error": {"code","message"}}`; structured logging that never logs request bodies.
5. `.env.example` with all variables (no real values).
6. Mobile skeleton (`mobile/`): `flutter create --platforms=android --org com.receiptbox`, Riverpod + go_router + Dio wired, `API_BASE_URL` via `--dart-define`, one placeholder screen calling `/health`. `flutter_lints` enabled. Turkish locale (`flutter_localizations`, `intl`) set to `tr_TR`.
7. GitHub Actions `ci.yml`: job `backend` (uv, ruff, pytest with postgres service) and job `mobile` (flutter analyze, flutter test).
8. Copy-check that `CLAUDE.md`, the skill, and `docs/` exist and are referenced in README.

## Out of scope

Any table besides what's needed for the health check, auth, real screens, AI code.

## Deliverables

`infra/docker-compose.yml`, `backend/{pyproject.toml,Dockerfile,app/main.py,app/core/*}`, `backend/tests/test_health.py`, `mobile/` skeleton, `.github/workflows/ci.yml`, `.env.example`, `README.md`.

## Acceptance criteria

- [x] `docker compose -f infra/docker-compose.yml up -d` starts db + backend; `curl localhost:8000/api/v1/health` → `{"status":"ok","db":"ok"}`.
- [x] `uv run pytest -q` passes (health test uses a test DB).
- [x] `flutter analyze` clean; `flutter test` passes; app runs on an Android emulator and shows "Sunucu: bağlı".
- [x] CI workflow passes on push. *(2026-11-16: run on `3ccbdb3`, jobs `backend` and `mobile` both succeeded)*
- [x] No secrets committed; `.env.example` complete.

## Tests

`test_health.py` (db up), one Flutter widget test for the placeholder screen.

## Manual check for the owner

Follow README on Windows: install Docker Desktop, Flutter, Android Studio emulator; run the three commands; see the app connect.
