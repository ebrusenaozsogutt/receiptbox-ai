"""Receipt extraction: masked text -> provider -> validation -> a PENDING_REVIEW observation.

The consent check (spec 15.3) and the rate limit are done by the API layer before this runs.
Nothing here logs receipt content. A rejected or failed extraction saves nothing.
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider, ExtractionHints, ProviderError
from app.ai.schemas import Confidence, RawReceiptExtraction, ReceiptExtraction
from app.ai.validation import ExtractionRejected, ValidationResult, validate_receipt
from app.core.errors import ExtractionFailedError, ExtractionRejectedError, TextTooLargeError
from app.core.text import normalize_alias_key
from app.models.enums import Direction, ObservationSource, ObservationStatus
from app.repositories.observations import ObservationRepository

logger = logging.getLogger("receiptbox.extraction")

MAX_TEXT_BYTES = 20 * 1024  # spec 15.2
BUSINESS_TIMEZONE = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class ExtractionOutcome:
    observation_id: uuid.UUID
    extraction: ReceiptExtraction
    confidence: dict[str, Confidence]


def business_today() -> date:
    return datetime.now(UTC).astimezone(BUSINESS_TIMEZONE).date()


def compute_fingerprint(
    *,
    source: str,
    merchant_raw: str | None,
    amount_minor: int | None,
    obs_date: date | None,
    obs_time: str | None,
    installment_seq: int | None = None,
) -> str:
    """Spec 7.2: sha256(source | merchant_normalized | amount_minor | obs_date | obs_time or ""
    | installment_seq or ""). The merchant normalisation is only step 1 of spec 5.6 for now
    (P06 completes it), so this is a placeholder that P06/P09 may recompute."""
    parts = [
        source,
        normalize_alias_key(merchant_raw or ""),
        "" if amount_minor is None else str(amount_minor),
        "" if obs_date is None else obs_date.isoformat(),
        obs_time or "",
        "" if installment_seq is None else str(installment_seq),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class ExtractionService:
    def __init__(
        self,
        session: AsyncSession,
        provider: AIProvider,
        *,
        today: date | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._observations = ObservationRepository(session)
        self._today = today

    async def extract_receipt(
        self,
        user_id: uuid.UUID,
        *,
        masked_text: str,
        capture_date: date,
        source: str,
    ) -> ExtractionOutcome:
        if len(masked_text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise TextTooLargeError()

        hints = ExtractionHints(capture_date=capture_date, source=source)
        try:
            # The SDK call is blocking: keep it off the event loop.
            raw = await asyncio.to_thread(self._provider.extract_receipt, masked_text, hints)
        except ProviderError as error:
            logger.warning("extraction_failed", extra={"error_type": type(error).__name__})
            raise ExtractionFailedError() from None

        try:
            result = validate_receipt(raw, masked_text, self._today or business_today())
        except ExtractionRejected as rejected:
            logger.warning("extraction_rejected", extra={"error_type": rejected.reason})
            raise ExtractionRejectedError() from None

        observation_id = await self._store(user_id, masked_text, raw, result)
        await self._session.commit()
        return ExtractionOutcome(
            observation_id=observation_id,
            extraction=result.extraction,
            confidence=result.confidence,
        )

    async def _store(
        self,
        user_id: uuid.UUID,
        masked_text: str,
        raw: RawReceiptExtraction,
        result: ValidationResult,
    ) -> uuid.UUID:
        extraction = result.extraction
        observation = await self._observations.add(
            user_id,
            source=ObservationSource.RECEIPT,
            status=ObservationStatus.PENDING_REVIEW,
            merchant_raw=extraction.merchant_raw,
            amount_minor=result.total_minor,
            direction=Direction.DEBIT,
            obs_date=extraction.date,
            obs_time=extraction.time,
            installment_count=extraction.installment_count,
            fingerprint=compute_fingerprint(
                source=ObservationSource.RECEIPT.value,
                merchant_raw=extraction.merchant_raw,
                amount_minor=result.total_minor,
                obs_date=extraction.date,
                obs_time=extraction.time.isoformat() if extraction.time else None,
            ),
            masked_text=masked_text,
            extraction_json={
                "extraction": extraction.model_dump(mode="json"),
                "llm_output": raw.model_dump(mode="json"),
                "issues": result.issues,
                "meta": {
                    "provider": self._provider.name,
                    "model": self._provider.model,
                    "prompt_version": self._provider.prompt_version,
                },
            },
            field_confidence_json={name: level.value for name, level in result.confidence.items()},
        )
        for item in result.items:
            await self._observations.add_receipt_item(
                user_id,
                observation.id,
                name_raw=item.name_raw,
                quantity=item.quantity if item.quantity is not None else Decimal(1),
                unit_price_minor=item.unit_price_minor,
                total_price_minor=item.total_price_minor,
            )
        return observation.id
