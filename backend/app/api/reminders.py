"""Reminders for local notifications (spec 12, 16, P13). No logic here: see
services/reminder_service.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, ReminderServiceDep
from app.schemas.errors import ErrorResponse
from app.schemas.reminders import ReminderList

router = APIRouter(prefix="/reminders", tags=["reminders"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}


@router.get(
    "/upcoming",
    response_model=ReminderList,
    responses={**_UNAUTHORIZED, 422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"}},
)
async def upcoming(
    user: CurrentUser,
    service: ReminderServiceDep,
    days: Annotated[int, Query(ge=1, le=366)] = 60,
) -> ReminderList:
    """Reminders that are not dismissed, from one day ago up to `days` ahead, soonest first. The
    phone schedules them as local notifications (no server push)."""
    return await service.upcoming(user.id, days)


@router.post(
    "/{reminder_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **_UNAUTHORIZED,
        404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"},
    },
)
async def dismiss(
    reminder_id: uuid.UUID, user: CurrentUser, service: ReminderServiceDep
) -> Response:
    """Stop this reminder (idempotent)."""
    await service.dismiss(user.id, reminder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
