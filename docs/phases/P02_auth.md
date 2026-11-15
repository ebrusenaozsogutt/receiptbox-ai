# P02 — Backend Authentication

**Goal:** Secure email/password auth with rotating refresh tokens and account deletion.
**Depends on:** P01 · **Week:** 2
**Read first:** spec §15.2, §16 (Auth rows)

## Scope

1. `POST /auth/register` {email, password, is_adult_confirmed=true required} → 201 + tokens. Password ≥ 8 chars, at least one letter and one digit. E-mail lowercased, unique.
2. `POST /auth/login` → access (JWT, 15 min, `sub`=user_id) + refresh (opaque random 256-bit, stored as SHA-256 hash, 30 days).
3. `POST /auth/refresh` → rotates: old token revoked + `replaced_by`; **reuse of a revoked token revokes the whole family** and returns 401.
4. `POST /auth/logout` → revokes the given refresh token.
5. `GET /me`, `DELETE /me` (deletes user, all rows via cascades, and the user's storage folder).
6. `get_current_user` dependency; 401 with code `AUTH_INVALID_TOKEN` / `AUTH_EXPIRED`.
7. Argon2id via argon2-cffi with sane parameters; constant-time comparisons.
8. Simple in-process rate limiter for `/auth/login` (5/min per email+IP).

## Out of scope

OAuth (Google/Apple), e-mail verification, password reset e-mails (document as future work).

## Acceptance criteria

- [ ] Register/login/refresh/logout/me/delete work and match OpenAPI schemas.
- [ ] Refresh rotation and reuse detection tested.
- [ ] Expired access token → 401 `AUTH_EXPIRED`.
- [ ] `DELETE /me` removes all user rows (test inserts rows in several tables first).
- [ ] Passwords never logged or returned; hashes are Argon2id.

## Tests

`tests/api/test_auth.py` (happy paths, wrong password, duplicate e-mail, rotation, reuse, rate limit), `tests/test_delete_account.py`.

## Manual check for the owner

Use `/docs` (Swagger UI): register, login, call `/me` with the token, refresh twice, try the old refresh token → 401.
