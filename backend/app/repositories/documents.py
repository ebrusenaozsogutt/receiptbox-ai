"""Documents (metadata of stored files). Every method takes `user_id` and filters by it."""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.models.enums import DocumentType
from app.repositories.base import UserScopedRepository, _check_user_id

# The pictures a receipt or an e-invoice leaves behind. A bank row or a manual entry never has one.
RECORD_PICTURE_TYPES = (DocumentType.RECEIPT_IMAGE, DocumentType.INVOICE)


class DocumentRepository(UserScopedRepository[Document]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Document)

    async def move_record_pictures(
        self, user_id: uuid.UUID, from_transaction_id: uuid.UUID, to_transaction_id: uuid.UUID
    ) -> int:
        """Move the receipt / invoice pictures (not the ones that belong to a product) from one
        purchase to another. Returns how many moved."""
        _check_user_id(user_id)
        result = await self._session.execute(
            update(Document)
            .where(
                Document.user_id == user_id,
                Document.transaction_id == from_transaction_id,
                Document.product_id.is_(None),
                Document.type.in_(RECORD_PICTURE_TYPES),
            )
            .values(transaction_id=to_transaction_id)
        )
        return result.rowcount  # type: ignore[attr-defined]
