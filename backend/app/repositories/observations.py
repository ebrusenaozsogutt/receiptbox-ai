"""Observations (evidence rows) and their receipt items.

`receipt_items` has no user_id column (spec 6.1): items are only created together with their
observation, in this repository, and read through the observation (which is user-scoped).
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Observation, ReceiptItem
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
        quantity: Decimal,
        unit_price_minor: int | None,
        total_price_minor: int | None,
    ) -> ReceiptItem:
        # The observation must be the caller's: an item can never be attached to someone else's.
        await self.require(user_id, observation_id)
        item = ReceiptItem(
            observation_id=observation_id,
            name_raw=name_raw,
            quantity=quantity,
            unit_price_minor=unit_price_minor,
            total_price_minor=total_price_minor,
        )
        self._session.add(item)
        await self._session.flush()
        return item
