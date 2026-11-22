"""Matching endpoints (spec 16, P09): the suggestions waiting for an answer, accept, reject."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, TransactionServiceDep
from app.models.enums import MatchDecisionStatus
from app.schemas.errors import ErrorResponse
from app.schemas.matches import MatchOut
from app.schemas.transactions import TransactionDetail

router = APIRouter(prefix="/matches", tags=["matching"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}
_CONFLICT = {
    409: {"model": ErrorResponse, "description": "MATCH_NOT_PENDING or MATCH_NOT_AVAILABLE"}
}


@router.get("", response_model=list[MatchOut], responses=_UNAUTHORIZED)
async def list_matches(
    user: CurrentUser,
    service: TransactionServiceDep,
    decision: MatchDecisionStatus = MatchDecisionStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MatchOut]:
    """Decisions of one kind, newest first. PENDING (the default) are the suggestions waiting for
    the user: "this may be the same as that purchase". Each carries the score and the features."""
    return await service.list_matches(user.id, decision, limit=limit, offset=offset)


@router.post(
    "/{decision_id}/accept",
    response_model=TransactionDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_CONFLICT},
)
async def accept_match(
    decision_id: uuid.UUID, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail:
    """ "Birleştir": the waiting observation is attached to the suggested purchase (the higher
    source wins the fields, spec 7.5). The other suggestions of the same observation are closed."""
    return await service.accept_match(user.id, decision_id)


@router.post(
    "/{decision_id}/reject",
    response_model=TransactionDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_CONFLICT},
)
async def reject_match(
    decision_id: uuid.UUID, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail:
    """ "Ayrı kalsın": every open suggestion of the observation is closed and a NEW purchase is
    created from what the user reviewed."""
    return await service.reject_match(user.id, decision_id)
