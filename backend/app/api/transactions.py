"""Transaction endpoints (spec 16): list, detail, manual entry, edit, delete."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, TransactionServiceDep
from app.models.enums import CategoryKey
from app.schemas.errors import ErrorResponse
from app.schemas.transactions import (
    ManualTransactionRequest,
    TransactionDetail,
    TransactionList,
    TransactionPatch,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}


@router.get("", response_model=TransactionList, responses=_UNAUTHORIZED)
async def list_transactions(
    user: CurrentUser,
    service: TransactionServiceDep,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    category: CategoryKey | None = None,
    merchant_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionList:
    """The user's purchases, newest first, with the count and the net total of everything that
    matches the filters (all pages), so the list can be checked against a hand calculation."""
    return await service.list(
        user.id,
        date_from=date_from,
        date_to=date_to,
        category=category,
        merchant_id=merchant_id,
        search=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=TransactionDetail,
    status_code=status.HTTP_201_CREATED,
    responses=_UNAUTHORIZED,
)
async def create_manual_transaction(
    body: ManualTransactionRequest, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail:
    """A purchase entered by hand: creates a MANUAL observation and the transaction."""
    return await service.create_manual(user.id, body)


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_transaction(
    transaction_id: uuid.UUID, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail:
    """One purchase with its evidence (receipt, QR, manual ...), items and documents."""
    return await service.detail(user.id, transaction_id)


@router.patch(
    "/{transaction_id}",
    response_model=TransactionDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def patch_transaction(
    transaction_id: uuid.UUID,
    body: TransactionPatch,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> TransactionDetail:
    return await service.patch(user.id, transaction_id, body)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def delete_transaction(
    transaction_id: uuid.UUID, user: CurrentUser, service: TransactionServiceDep
) -> Response:
    """Soft delete. Its receipt images are deleted too; its evidence stays (unlinked)."""
    await service.delete(user.id, transaction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
