"""Users table access.

Two lookups here are *not* scoped by user_id, on purpose: finding an account by e-mail
(register, login) happens before we know who the user is. Everything that comes after
(`get`, `delete`, ...) is keyed by user_id.
"""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """Credential lookup for register/login. `email` must already be lowercased."""
        return (
            await self._session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def get(self, user_id: uuid.UUID) -> User | None:
        return (
            await self._session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    async def add(self, *, email: str, password_hash: str, is_adult_confirmed: bool) -> User:
        user = User(email=email, password_hash=password_hash, is_adult_confirmed=is_adult_confirmed)
        self._session.add(user)
        await self._session.flush()
        return user

    async def set_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(password_hash=password_hash)
        )

    async def set_ai_consent(self, user_id: uuid.UUID, value: bool) -> None:
        await self._session.execute(update(User).where(User.id == user_id).values(ai_consent=value))

    async def delete(self, user_id: uuid.UUID) -> bool:
        """Delete the user; foreign-key cascades remove every row they own."""
        result = await self._session.execute(delete(User).where(User.id == user_id))
        return result.rowcount > 0  # type: ignore[attr-defined]
