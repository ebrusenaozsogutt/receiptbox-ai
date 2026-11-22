"""Transaction endpoints (spec 16): list, detail, manual entry, edit, delete."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, TransactionServiceDep
from app.models.enums import CategoryKey
from app.schemas.errors import ErrorResponse
from app.schemas.matches import SuggestionResponse, UnmergeRequest
from app.schemas.transactions import (
    ManualTransactionRequest,
    TransactionDetail,
    TransactionList,
    TransactionPatch,
    UnmergeResponse,
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
    responses={
        **_UNAUTHORIZED,
        202: {
            "model": SuggestionResponse,
            "description": "It may be a purchase you already have: no purchase exists yet, "
            "answer with POST /matches/{id}/accept or /reject.",
        },
    },
)
async def create_manual_transaction(
    body: ManualTransactionRequest, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail | JSONResponse:
    """A purchase entered by hand: creates a MANUAL observation and the transaction, unless it is
    the same purchase as one you already have (`outcome` MERGED: attached to it) or may be
    (202: the app asks first)."""
    result = await service.create_manual(user.id, body)
    if isinstance(result, SuggestionResponse):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=result.model_dump(mode="json")
        )
    return result


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


@router.post(
    "/{transaction_id}/unmerge",
    response_model=UnmergeResponse,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "NOT_MERGED"},
    },
)
async def unmerge_transaction(
    transaction_id: uuid.UUID,
    body: UnmergeRequest,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> UnmergeResponse:
    """ "Ayır" / "Geri al": the observation `observation_id` leaves this purchase and becomes a
    purchase of its own; the other record keeps the old one. The decision is logged `UNDONE`."""
    return await service.unmerge(user.id, transaction_id, body.observation_id)


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
