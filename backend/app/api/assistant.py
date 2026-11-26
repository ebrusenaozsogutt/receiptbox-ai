"""The AI assistant (spec 13, P14). No logic here: see services/assistant_service.py."""

from fastapi import APIRouter, Response, status

from app.api.deps import AssistantChatServiceDep, AssistantServiceDep, AssistantUser, CurrentUser
from app.schemas.assistant import ActionOut, ChatIn, ChatOut, ToolCallOut
from app.schemas.errors import ErrorResponse
from app.services.assistant_service import HistoryTurn

router = APIRouter(prefix="/assistant", tags=["assistant"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}


@router.post(
    "/chat",
    response_model=ChatOut,
    responses={
        **_UNAUTHORIZED,
        403: {"model": ErrorResponse, "description": "AI_CONSENT_REQUIRED"},
        422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"},
        429: {"model": ErrorResponse, "description": "RATE_LIMITED (20 questions per minute)"},
        503: {"model": ErrorResponse, "description": "ASSISTANT_UNAVAILABLE (timeout, quota)"},
    },
)
async def chat(user: AssistantUser, service: AssistantChatServiceDep, body: ChatIn) -> ChatOut:
    """Answers a Turkish question about the user's own purchases, products, warranties,
    installments and documents, using only tool results of this turn. Needs the AI consent."""
    result = await service.chat(
        user.id,
        body.message.strip(),
        [HistoryTurn(t.question, t.answer) for t in body.history],
    )
    return ChatOut(
        answer=result.answer,
        actions=[ActionOut(**a.as_dict()) for a in result.actions],
        tool_calls=[ToolCallOut(**c.as_dict()) for c in result.tool_calls],
    )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT, responses=_UNAUTHORIZED)
async def clear_history(user: CurrentUser, service: AssistantServiceDep) -> Response:
    """Deletes every stored question and answer of the user (works without the AI consent)."""
    await service.clear_history(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
