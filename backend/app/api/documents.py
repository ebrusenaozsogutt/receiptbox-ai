"""Document endpoints (spec 16): upload, metadata, access token, content, delete."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DocumentServiceDep
from app.models.enums import DocumentType
from app.schemas.documents import DocumentAccessToken, DocumentOut
from app.schemas.errors import ErrorResponse
from app.services.document_service import read_limited

router = APIRouter(prefix="/documents", tags=["documents"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}


async def _chunks(upload: UploadFile):  # type: ignore[no-untyped-def]
    while chunk := await upload.read(64 * 1024):
        yield chunk


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        413: {"model": ErrorResponse, "description": "FILE_TOO_LARGE (over 10 MB)"},
        415: {"model": ErrorResponse, "description": "UNSUPPORTED_FILE_TYPE (jpeg, png, pdf only)"},
    },
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    service: DocumentServiceDep,
    type: Annotated[DocumentType, Form()] = DocumentType.RECEIPT_IMAGE,  # noqa: A002
    transaction_id: Annotated[uuid.UUID | None, Form()] = None,
    product_id: Annotated[uuid.UUID | None, Form()] = None,
) -> DocumentOut:
    """Store a receipt image, an invoice PDF or another file privately (jpeg, png or pdf, up
    to 10 MB). The type is decided from the file's first bytes, not from its name."""
    data = await read_limited(_chunks(file))
    document = await service.upload(
        user.id,
        data=data,
        document_type=type,
        transaction_id=transaction_id,
        product_id=product_id,
    )
    return DocumentOut.model_validate(document)


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_document(
    document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep
) -> DocumentOut:
    return DocumentOut.model_validate(await service.get(user.id, document_id))


@router.post(
    "/{document_id}/access-token",
    response_model=DocumentAccessToken,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def create_access_token(
    document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep
) -> DocumentAccessToken:
    """A token that lets the app show THIS document for 5 minutes (an image view cannot send
    the Authorization header)."""
    token, expires_in = await service.create_access_token(user.id, document_id)
    return DocumentAccessToken(
        token=token,
        expires_in=expires_in,
        content_url=f"/documents/{document_id}/content?token={token}",
    )


@router.get(
    "/{document_id}/content",
    responses={
        200: {"description": "The file", "content": {"image/jpeg": {}, "image/png": {}}},
        401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"},
        **_NOT_FOUND,
    },
)
async def get_document_content(
    document_id: uuid.UUID,
    service: DocumentServiceDep,
    token: Annotated[str, Query(max_length=2048)],
) -> Response:
    """The file itself. Needs no Authorization header, only the token of
    `POST /documents/{id}/access-token` (valid 5 minutes, for this document only)."""
    data, mime_type = await service.content(document_id, token)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep
) -> Response:
    await service.delete(user.id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
