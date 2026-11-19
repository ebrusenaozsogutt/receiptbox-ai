"""Observations (evidence rows) and their receipt items.

`receipt_items` has no user_id column (spec 6.1): items are only created together with their
observation, in this repository, and read through the observation (which is user-scoped).
"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Observation, ReceiptItem
from app.models.enums import ObservationStatus
from app.repositories.base import UserScopedRepository


class ObservationRepository(UserScopedRepository[Observation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Observation)

    async def add_receipt_item(
        self,
        user_id: uuid.UUID,
        observation_id: uuid.UUID,
        *,
        name_raw: str,
        position: int = 0,
        quantity: Decimal,
        unit_price_minor: int | None,
        total_price_minor: int | None,
    ) -> ReceiptItem:
        # The observation must be the caller's: an item can never be attached to someone else's.
        await self.require(user_id, observation_id)
        item = ReceiptItem(
            observation_id=observation_id,
            name_raw=name_raw,
            position=position,
            quantity=quantity,
            unit_price_minor=unit_price_minor,
            total_price_minor=total_price_minor,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def list_by_status(
        self, user_id: uuid.UUID, status: ObservationStatus, *, limit: int, offset: int
    ) -> list[Observation]:
        """The user's observations in one status, newest first."""
        rows = await self.list(
            user_id,
            where=[Observation.status == status],
            order_by=[Observation.created_at.desc(), Observation.id],
            limit=limit,
            offset=offset,
        )
        return list(rows)

    async def items_of(
        self, user_id: uuid.UUID, observation_ids: list[uuid.UUID]
    ) -> list[ReceiptItem]:
        """Items of the user's own observations only (other ids are silently ignored)."""
        if not observation_ids:
            return []
        statement = (
            select(ReceiptItem)
            .join(Observation, Observation.id == ReceiptItem.observation_id)
            .where(Observation.user_id == user_id, ReceiptItem.observation_id.in_(observation_ids))
            .order_by(ReceiptItem.observation_id, ReceiptItem.position, ReceiptItem.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def replace_items(
        self, user_id: uuid.UUID, observation_id: uuid.UUID, items: list[dict]
    ) -> None:
        """Replace the items of one of the user's observations with the reviewed ones."""
        await self.require(user_id, observation_id)
        await self._session.execute(
            delete(ReceiptItem).where(ReceiptItem.observation_id == observation_id)
        )
        for position, item in enumerate(items):
            await self.add_receipt_item(user_id, observation_id, position=position, **item)
