"""Extraction endpoints (spec 16). P05: POST /extract/receipt."""

from fastapi import APIRouter

from app.api.deps import ExtractionServiceDep, ExtractionUser
from app.schemas.errors import ErrorResponse
from app.schemas.extraction import ExtractReceiptRequest, ExtractReceiptResponse

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post(
    "/receipt",
    response_model=ExtractReceiptResponse,
    responses={
        401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"},
        403: {"model": ErrorResponse, "description": "AI_CONSENT_REQUIRED"},
        413: {"model": ErrorResponse, "description": "TEXT_TOO_LARGE (over 20 KB)"},
        422: {"model": ErrorResponse, "description": "EXTRACTION_REJECTED (absurd amount)"},
        429: {"model": ErrorResponse, "description": "RATE_LIMITED (20 per minute)"},
        502: {"model": ErrorResponse, "description": "EXTRACTION_FAILED (AI provider problem)"},
    },
)
async def extract_receipt(
    body: ExtractReceiptRequest, user: ExtractionUser, service: ExtractionServiceDep
) -> ExtractReceiptResponse:
    """Masked receipt text -> validated extraction with per-field confidence.

    Saves a PENDING_REVIEW observation (the user reviews it in P07). Nothing is saved when the
    extraction fails or is rejected. Needs the AI consent (PUT /me/ai-consent).
    """
    outcome = await service.extract_receipt(
        user.id,
        masked_text=body.masked_text,
        capture_date=body.capture_date,
        source=body.source,
    )
    return ExtractReceiptResponse(
        observation_id=outcome.observation_id,
        extraction=outcome.extraction,
        confidence=outcome.confidence,
    )
