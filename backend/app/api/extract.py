"""Extraction endpoints (spec 16): receipt, e-invoice QR and bank screenshot."""

from fastapi import APIRouter

from app.api.deps import BankServiceDep, ExtractionCaller, ExtractionServiceDep, ExtractionUser
from app.schemas.errors import ErrorResponse
from app.schemas.extraction import (
    BankRowOut,
    ExtractBankRequest,
    ExtractBankResponse,
    ExtractEinvoiceRequest,
    ExtractEinvoiceResponse,
    ExtractReceiptRequest,
    ExtractReceiptResponse,
    SkippedRowOut,
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


@router.post(
    "/bank-screenshot",
    response_model=ExtractBankResponse,
    responses={
        401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"},
        403: {"model": ErrorResponse, "description": "AI_CONSENT_REQUIRED"},
        413: {"model": ErrorResponse, "description": "TEXT_TOO_LARGE (over 20 KB)"},
        422: {
            "model": ErrorResponse,
            "description": "BANK_SCREEN_NOT_SUPPORTED (a current-account screen)",
        },
        429: {"model": ErrorResponse, "description": "RATE_LIMITED (20 per minute)"},
        502: {"model": ErrorResponse, "description": "EXTRACTION_FAILED (AI provider problem)"},
    },
)
async def extract_bank_screenshot(
    body: ExtractBankRequest, user: ExtractionUser, service: BankServiceDep
) -> ExtractBankResponse:
    """Masked text of a bank screenshot -> its rows, each saved as a PENDING_REVIEW observation.

    The screenshot itself never reaches the server. Card-bill payments, loyalty points, totals and
    zero amounts come back in `skipped` and are not saved. A row imported before has status
    DUPLICATE. Needs the AI consent (PUT /me/ai-consent).
    """
    outcome = await service.extract(
        user.id,
        masked_text=body.masked_text,
        bank_hint=body.bank_hint,
        capture_date=body.capture_date,
    )
    return ExtractBankResponse(
        bank_key=outcome.bank_key,
        rows=[
            BankRowOut(
                observation_id=item.observation_id,
                merchant_raw=item.row.merchant_raw,
                amount_minor=item.row.amount_minor,
                direction=item.row.direction,
                kind=item.row.kind,  # type: ignore[arg-type]
                date=item.row.obs_date,
                time=item.row.obs_time,
                installment_seq=item.row.installment_seq,
                installment_count=item.row.installment_count,
                is_pending=item.row.is_pending,
                status=item.status.value,  # type: ignore[arg-type]
                possible_refund=item.row.kind == "REFUND",
                confidence=item.row.confidence,
                suggestions=item.suggestions,
                match=item.match,
                installment=item.installment,
            )
            for item in outcome.rows
        ],
        skipped=[
            SkippedRowOut(
                merchant_raw=row.merchant_raw,
                amount_minor=row.amount_minor,
                date=row.obs_date,
                reason=row.reason,
            )
            for row in outcome.skipped
        ],
    )
