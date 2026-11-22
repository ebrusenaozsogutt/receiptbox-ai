"""Match decisions (the audit log of merges). Every method takes `user_id` and filters by it."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select

from app.models import MatchDecision
from app.models.enums import MatchDecisionStatus
from app.repositories.base import UserScopedRepository, _check_user_id


class MatchDecisionRepository(UserScopedRepository[MatchDecision]):
    def __init__(self, session) -> None:  # noqa: ANN001
        super().__init__(session, MatchDecision)

    async def pending_for_observation(
        self, user_id: uuid.UUID, observation_id: uuid.UUID
    ) -> Sequence[MatchDecision]:
        return await self.list(
            user_id,
            where=[
                MatchDecision.observation_id == observation_id,
                MatchDecision.decision == MatchDecisionStatus.PENDING,
            ],
            order_by=[MatchDecision.score.desc(), MatchDecision.id],
        )

    async def delete_pending_for_observation(
        self, user_id: uuid.UUID, observation_id: uuid.UUID
    ) -> None:
        """A new evaluation replaces the open ones of the same observation (decided ones stay:
        they are the labels P15 learns from)."""
        _check_user_id(user_id)
        await self._session.execute(
            delete(MatchDecision).where(
                MatchDecision.user_id == user_id,
                MatchDecision.observation_id == observation_id,
                MatchDecision.decision == MatchDecisionStatus.PENDING,
            )
        )

    async def with_status(
        self, user_id: uuid.UUID, status: MatchDecisionStatus, *, limit: int, offset: int
    ) -> Sequence[MatchDecision]:
        return await self.list(
            user_id,
            where=[MatchDecision.decision == status],
            order_by=[MatchDecision.created_at.desc(), MatchDecision.id],
            limit=limit,
            offset=offset,
        )

    async def active_merges_of(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Sequence[MatchDecision]:
        """The accepted decisions that attached an observation to this transaction."""
        _check_user_id(user_id)
        statement = (
            select(MatchDecision)
            .where(
                MatchDecision.user_id == user_id,
                MatchDecision.transaction_id == transaction_id,
                MatchDecision.decision.in_(
                    [MatchDecisionStatus.ACCEPTED, MatchDecisionStatus.AUTO_ACCEPTED]
                ),
                MatchDecision.merge_snapshot.is_not(None),
            )
            .order_by(MatchDecision.created_at.desc())
        )
        return (await self._session.execute(statement)).scalars().all()
