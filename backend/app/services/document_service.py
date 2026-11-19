"""Documents: store a file privately, hand it out through a short-lived token, delete it.

Rules (spec 15.2): jpeg, png or pdf only, at most 10 MB, decided from the file's first bytes (not
from what the client claims); a stored name is a random UUID; the bytes are only ever returned
for a valid, unexpired token that names exactly this document.
"""

import asyncio
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    FileTooLargeError,
    InvalidTokenError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from app.models import Document, Transaction
from app.models.enums import DocumentType
from app.repositories.documents import DocumentRepository
from app.security.document_tokens import (
    DOCUMENT_TOKEN_TTL,
    create_document_token,
    decode_document_token,
)
from app.storage.backend import StorageBackend, StorageError

logger = logging.getLogger("receiptbox.documents")

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # spec 15.2
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


def detect_mime_type(data: bytes) -> str | None:
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


async def read_limited(chunks: AsyncIterator[bytes]) -> bytes:
    """Read an upload, refusing to hold more than the limit in memory."""
    received = bytearray()
    async for chunk in chunks:
        received.extend(chunk)
        if len(received) > MAX_DOCUMENT_BYTES:
            raise FileTooLargeError()
    return bytes(received)


class DocumentService:
    def __init__(self, session: AsyncSession, storage: StorageBackend, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._documents = DocumentRepository(session)

    async def upload(
        self,
        user_id: uuid.UUID,
        *,
        data: bytes,
        document_type: DocumentType,
        transaction_id: uuid.UUID | None,
    ) -> Document:
        if len(data) > MAX_DOCUMENT_BYTES:
            raise FileTooLargeError()
        mime_type = detect_mime_type(data)
        if mime_type is None:
            raise UnsupportedFileTypeError()
        if transaction_id is not None:
            await self._require_own_transaction(user_id, transaction_id)

        key = self._storage.new_key(user_id)
        await self._run(self._storage.save, key, data)
        try:
            document = await self._documents.add(
                user_id,
                type=document_type,
                storage_key=key,
                mime_type=mime_type,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                transaction_id=transaction_id,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            await self._forget_file(key)  # no row, so no file either
            raise
        return document

    async def get(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        return await self._documents.require(user_id, document_id)

    async def create_access_token(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[str, int]:
        await self._documents.require(user_id, document_id)  # 404 for someone else's document
        token = create_document_token(
            user_id, document_id, self._settings.jwt_secret.get_secret_value()
        )
        return token, int(DOCUMENT_TOKEN_TTL.total_seconds())

    async def content(self, document_id: uuid.UUID, token: str) -> tuple[bytes, str]:
        """The bytes and the mime type, for a token that is valid and names THIS document."""
        user_id, token_document_id = decode_document_token(
            token, self._settings.jwt_secret.get_secret_value()
        )
        if token_document_id != document_id:
            raise InvalidTokenError()
        document = await self._documents.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        try:
            data = await self._run(self._storage.read, document.storage_key)
        except StorageError:
            logger.error("document_file_missing")
            raise NotFoundError() from None
        return data, document.mime_type

    async def delete(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self._documents.require(user_id, document_id)
        key = document.storage_key
        await self._documents.delete(user_id, document_id)
        await self._session.commit()
        await self._forget_file(key)

    async def list_for_transaction(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> list[Document]:
        rows = await self._session.execute(
            select(Document)
            .where(Document.user_id == user_id, Document.transaction_id == transaction_id)
            .order_by(Document.created_at)
        )
        return list(rows.scalars().all())

    async def _require_own_transaction(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        found = (
            await self._session.execute(
                select(Transaction.id).where(
                    Transaction.id == transaction_id,
                    Transaction.user_id == user_id,
                    Transaction.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if found is None:
            raise NotFoundError()

    async def _forget_file(self, key: str) -> None:
        try:
            await self._run(self._storage.delete, key)
        except StorageError:
            # The row is already gone; leave a trace without the key.
            logger.error("document_file_cleanup_failed")

    @staticmethod
    def _run[**P, R](function: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        return asyncio.to_thread(function, *args, **kwargs)
