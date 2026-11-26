"""Stored assistant turns (P14; spec 6.1 `assistant_turns`). Every method takes `user_id`."""

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssistantTurn
from app.models.enums import AssistantOutcome


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


class AssistantTurnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        user_id: uuid.UUID,
        *,
        question: str,
        tool_calls: list[dict[str, Any]],
        answer: str | None,
        actions: list[dict[str, Any]],
        latency_ms: int,
        outcome: AssistantOutcome,
        model: str,
        prompt_version: str,
    ) -> AssistantTurn:
        _check_user_id(user_id)
        turn = AssistantTurn(
            user_id=user_id,
            question=question,
            tool_calls_json=tool_calls,
            answer=answer,
            actions_json=actions,
            latency_ms=latency_ms,
            outcome=outcome,
            model=model,
            prompt_version=prompt_version,
        )
        self._session.add(turn)
        return turn

    async def delete_all(self, user_id: uuid.UUID) -> int:
        _check_user_id(user_id)
        result = await self._session.execute(
            delete(AssistantTurn).where(AssistantTurn.user_id == user_id)
        )
        return result.rowcount or 0
