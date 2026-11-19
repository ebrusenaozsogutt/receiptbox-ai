"""Documents (metadata of stored files). Every method takes `user_id` and filters by it."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.repositories.base import UserScopedRepository


class DocumentRepository(UserScopedRepository[Document]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Document)
