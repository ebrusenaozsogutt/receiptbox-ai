# P01 — Backend Data Model & Migrations

**Goal:** All MVP tables exist with constraints, plus seed data, so later phases only add logic.
**Depends on:** P00 · **Week:** 1
**Read first:** spec §5.7 (categories), §6 (entire), §10.2

## Scope

1. SQLAlchemy 2 ORM models in `app/models/` for every table in spec §6.1 (exact names and enums). Enums as PostgreSQL enums or `VARCHAR` + CHECK — pick one and use it consistently.
2. Common mixin: UUID pk (server default `gen_random_uuid()`), `created_at`, `updated_at`.
3. Money columns `*_minor BIGINT NOT NULL CHECK (>= 0)`; `currency CHAR(3) DEFAULT 'TRY'`.
4. Indexes: `transactions(user_id, purchase_date)`, `transactions(user_id, merchant_id)`, `observations(user_id, fingerprint)`, `observations(user_id, external_id)`, `installment_payments(plan_id, due_month)`, `reminders(user_id, fire_at)`, unique constraints from spec.
5. Alembic initial migration (autogenerate, then hand-review). Downgrade must work.
6. Seed migration/script: 13 categories (keys + Turkish labels + sort order); ~150 common Turkish merchants with default categories and a few global aliases each (`data/merchants_seed.csv`).
7. Repository base helper that requires `user_id` for user-owned models (e.g. `UserScopedRepository[T]` with `get(user_id, id)`, `list(user_id, ...)`).
8. Money helpers in `app/core/money.py`: parse Turkish strings (`1.349,90`, `1349.90`, `*494,60`) → minor units; format minor → `1.349,90`.

## Out of scope

Endpoints (except none), business logic, matching.

## Deliverables

`app/models/*.py`, `migrations/versions/0001_initial.py`, `0002_seed.py`, `data/merchants_seed.csv`, `app/repositories/base.py`, `app/core/money.py`, tests.

## Acceptance criteria

- [ ] `alembic upgrade head` and `alembic downgrade base` both succeed on an empty DB.
- [ ] All tables/columns/enums match spec §6.1 (a test introspects metadata for required columns).
- [ ] Seeds load: 13 categories, ≥ 150 merchants, aliases resolve (e.g. `MIGROS TICARET AS` → Migros).
- [ ] `UserScopedRepository` cannot be called without `user_id` (type-enforced) and filters correctly (test with 2 users).
- [ ] Money helpers handle ≥ 15 formats incl. negatives rejected, `494,6` → 49460.

## Tests

`test_models_schema.py`, `test_seed.py`, `test_money.py`, `test_user_scoped_repository.py`.

## Manual check for the owner

Open the DB with a client (e.g. DBeaver) and look at the tables; read `docs/spec` §6 side by side.
