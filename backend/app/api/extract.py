"""Extraction endpoints (spec 16): POST /extract/receipt and POST /extract/einvoice-qr."""

from fastapi import APIRouter

from app.api.deps import ExtractionCaller, ExtractionServiceDep, ExtractionUser
from app.schemas.errors import ErrorResponse
from app.schemas.extraction import (
    ExtractEinvoiceRequest,
    ExtractEinvoiceResponse,
    ExtractReceiptRequest,
    ExtractReceiptResponse,
)

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
    """Masked receipt text -> validated extraction with per-field confidence and merchant and
    category suggestions.

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
        suggestions=outcome.suggestions,
    )


@router.post(
    "/einvoice-qr",
    response_model=ExtractEinvoiceResponse,
    responses={
        401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"},
        413: {"model": ErrorResponse, "description": "TEXT_TOO_LARGE (over 20 KB)"},
        422: {
            "model": ErrorResponse,
            "description": "QR_INVALID (not a GİB invoice QR) or EXTRACTION_REJECTED",
        },
        429: {"model": ErrorResponse, "description": "RATE_LIMITED (20 per minute)"},
    },
)
async def extract_einvoice_qr(
    body: ExtractEinvoiceRequest, user: ExtractionCaller, service: ExtractionServiceDep
) -> ExtractEinvoiceResponse:
    """The QR of an e-Archive / e-Invoice -> observation (source EINVOICE_QR, QR fields HIGH).

    Works without the AI consent, because the QR is read without any AI. If `masked_text` is
    sent AND the user consented, the AI also reads merchant name and items from it (total and
    date always come from the QR); without consent the text is ignored (`ai_used` is false).
    """
    outcome = await service.extract_einvoice_qr(
        user.id,
        qr_payload=body.qr_payload,
        masked_text=body.masked_text,
        capture_date=body.capture_date,
        allow_ai=user.ai_consent,
    )
    return ExtractEinvoiceResponse(
        observation_id=outcome.observation_id,
        extraction=outcome.extraction,
        confidence=outcome.confidence,
        suggestions=outcome.suggestions,
        ai_used=outcome.ai_used,
    )
