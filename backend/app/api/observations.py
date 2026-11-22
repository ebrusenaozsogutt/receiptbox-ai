"""Observation endpoints (spec 16): the review queue, confirm and reject."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, TransactionServiceDep
from app.models.enums import ObservationStatus
from app.schemas.errors import ErrorResponse
from app.schemas.matches import SuggestionResponse
from app.schemas.transactions import (
    ConfirmBatchRequest,
    ConfirmBatchResponse,
    ConfirmRequest,
    ObservationOut,
    TransactionDetail,
)

router = APIRouter(prefix="/observations", tags=["observations"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}
_CONFLICT = {409: {"model": ErrorResponse, "description": "OBSERVATION_NOT_PENDING"}}


@router.get("", response_model=list[ObservationOut], responses=_UNAUTHORIZED)
async def list_observations(
    user: CurrentUser,
    service: TransactionServiceDep,
    status_filter: Annotated[ObservationStatus, Query(alias="status")] = (
        ObservationStatus.PENDING_REVIEW
    ),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ObservationOut]:
    """The user's observations in one status (default: waiting for review), newest first."""
    return await service.list_observations(user.id, status_filter, limit=limit, offset=offset)


@router.post(
    "/confirm-batch",
    response_model=ConfirmBatchResponse,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def confirm_batch(
    body: ConfirmBatchRequest, user: CurrentUser, service: TransactionServiceDep
) -> ConfirmBatchResponse:
    """Save the selected bank rows as purchases. Every id must be yours (404 for any other,
    nothing is saved). A credit row stays an observation flagged "possible refund"; rows that
    cannot be saved come back in `skipped` with a reason."""
    return await service.confirm_batch(user.id, body)


@router.post(
    "/{observation_id}/confirm",
    response_model=TransactionDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        **_CONFLICT,
        202: {
            "model": SuggestionResponse,
            "description": "It may be a purchase you already have: no purchase exists yet, "
            "answer with POST /matches/{id}/accept or /reject.",
        },
    },
)
async def confirm_observation(
    observation_id: uuid.UUID,
    body: ConfirmRequest,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> TransactionDetail | JSONResponse:
    """Save the reviewed receipt. The matching engine looks first (spec 7): the same purchase
    seen before (for example the bank row) takes the receipt in as evidence (`outcome` MERGED,
    `match.decision` AUTO_ACCEPTED: the app offers "Geri al"); a likely one answers 202 and the
    observation waits for POST /matches/{id}/accept or /reject; otherwise a NEW transaction is
    created, the observation linked to it and marked CONFIRMED. With
    `remember_category_for_merchant` the category becomes this user's rule for the merchant."""
    result = await service.confirm(user.id, observation_id, body)
    if isinstance(result, SuggestionResponse):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=result.model_dump(mode="json")
        )
    return result


@router.post(
    "/{observation_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_CONFLICT},
)
async def reject_observation(
    observation_id: uuid.UUID, user: CurrentUser, service: TransactionServiceDep
) -> Response:
    await service.reject(user.id, observation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
