"""Refresh token rows.

`get_by_hash_for_update` is *not* scoped by user_id on purpose: the client only presents the
token, so the owner is unknown until the row is found. Every method after that takes the
`user_id` of the found row and filters by it.

A token "family" is the chain of rows linked by `replaced_by` (each refresh creates a new
row and points the old one at it). Spec 6.1 has no family column, so the chain is walked.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, user_id: uuid.UUID, *, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Look the token up and lock its row, so two refreshes with the same token queue up."""
        statement = (
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def revoke(
        self,
        user_id: uuid.UUID,
        token_id: uuid.UUID,
        *,
        now: datetime,
        replaced_by: uuid.UUID | None = None,
    ) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.id == token_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, replaced_by=replaced_by)
        )

    async def revoke_family(self, user_id: uuid.UUID, token_id: uuid.UUID, *, now: datetime) -> int:
        """Revoke every still-active token reachable from `token_id` through `replaced_by`.

        Called when a revoked token is presented again (theft or replay): whoever holds the
        newest token of the chain is logged out too.
        """
        chain = (
            select(RefreshToken.id, RefreshToken.replaced_by)
            .where(RefreshToken.id == token_id, RefreshToken.user_id == user_id)
            .cte("token_chain", recursive=True)
        )
        chain = chain.union_all(
            select(RefreshToken.id, RefreshToken.replaced_by).where(
                RefreshToken.id == chain.c.replaced_by, RefreshToken.user_id == user_id
            )
        )
        result = await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.id.in_(select(chain.c.id)),
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        return result.rowcount  # type: ignore[attr-defined]
