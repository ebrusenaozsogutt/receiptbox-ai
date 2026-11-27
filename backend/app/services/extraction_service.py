"""Receipt and e-invoice QR extraction -> a PENDING_REVIEW observation.

Receipt text:  masked text -> provider -> validation -> suggestions -> observation.
GİB QR:        QR fields (deterministic, no AI) [+ masked text -> provider for merchant and
               items] -> suggestions -> observation.

Suggestions (spec 5.6 / 5.7): which merchant this probably is and which category, stored in
`extraction_json.suggestions` and returned. No merchant row is created here (DECISIONS): a NEW
merchant is only a proposed name until the user confirms (P07).

The consent check (spec 15.3) and the rate limit are done by the API layer before this runs;
`allow_ai` tells the QR path whether the user consented. Nothing here logs receipt content. A
rejected or failed extraction saves nothing.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import AIProvider, ExtractionHints, ProviderError
from app.ai.schemas import Confidence, RawReceiptExtraction, ReceiptExtraction, ReceiptItem
from app.ai.usage import DailyLimitReached
from app.ai.validation import (
    FIELDS,
    MAX_RECEIPT_AGE_YEARS,
    MAX_TOTAL_MINOR,
    ExtractionRejected,
    ParsedItem,
    ValidationResult,
    rate_items,
    validate_receipt,
)
from app.core.errors import (
    AiDailyLimitError,
    ExtractionFailedError,
    ExtractionRejectedError,
    InvalidQrError,
    TextTooLargeError,
)
from app.core.text import normalize_alias_key
from app.matching.merchant_normalizer import MerchantMatch, MerchantNormalizer
from app.models.enums import Direction, ObservationSource, ObservationStatus
from app.qr.gib_qr import GibQr, GibQrError, parse_gib_qr
from app.repositories.merchants import MerchantRepository
from app.repositories.observations import ObservationRepository
from app.schemas.extraction import CategorySuggestionOut, MerchantSuggestion, Suggestions
from app.services.categorization_service import CategorizationService

logger = logging.getLogger("receiptbox.extraction")

MAX_TEXT_BYTES = 20 * 1024  # spec 15.2
BUSINESS_TIMEZONE = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class ExtractionOutcome:
    observation_id: uuid.UUID
    extraction: ReceiptExtraction
    confidence: dict[str, Confidence]
    suggestions: Suggestions
    ai_used: bool = True


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
    external_id: str | None = None,
) -> str:
    """Spec 7.2: sha256(source | merchant_normalized | amount_minor | obs_date | obs_time or ""
    | installment_seq or ""). For QR observations the ETTN is used instead. `merchant_raw` is
    the canonical merchant name when the merchant is known (P06), else the cleaned name."""
    if external_id:
        return hashlib.sha256(f"{source}|{external_id}".encode()).hexdigest()
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
        merchants = MerchantRepository(session)
        self._normalizer = MerchantNormalizer(merchants)
        self._categorizer = CategorizationService(merchants, provider)
        self._today = today

    # ---- receipt text -------------------------------------------------------------------------

    async def extract_receipt(
        self,
        user_id: uuid.UUID,
        *,
        masked_text: str,
        capture_date: date,
        source: str,
    ) -> ExtractionOutcome:
        _check_size(masked_text)
        raw = await self._ask_provider(masked_text, capture_date, source, strict=True)
        if raw is None:
            raise ExtractionFailedError()

        try:
            result = validate_receipt(raw, masked_text, self._today or business_today())
        except ExtractionRejected as rejected:
            logger.warning("extraction_rejected", extra={"error_type": rejected.reason})
            raise ExtractionRejectedError() from None

        suggestions = await self._suggest(
            user_id,
            result.extraction.merchant_raw,
            [item.name_raw for item in result.items],
            allow_ai=True,
        )
        observation_id = await self._store(
            user_id,
            source=ObservationSource.RECEIPT,
            extraction=result.extraction,
            total_minor=result.total_minor,
            items=result.items,
            confidence=result.confidence,
            issues=result.issues,
            suggestions=suggestions,
            masked_text=masked_text,
            llm_output=raw,
            ai_used=True,
        )
        await self._session.commit()
        return ExtractionOutcome(
            observation_id=observation_id,
            extraction=result.extraction,
            confidence=result.confidence,
            suggestions=suggestions,
        )

    # ---- GİB e-invoice QR ---------------------------------------------------------------------

    async def extract_einvoice_qr(
        self,
        user_id: uuid.UUID,
        *,
        qr_payload: Mapping[str, Any] | str,
        masked_text: str | None,
        capture_date: date,
        allow_ai: bool,
    ) -> ExtractionOutcome:
        """The QR gives total, date and ETTN without any AI. When the user consented and the
        phone sent the invoice text too, the model adds merchant name and items (it never
        overrides the QR). Without consent the text is ignored: nothing is sent anywhere."""
        raw_size = qr_payload if isinstance(qr_payload, str) else json.dumps(qr_payload)
        _check_size(raw_size)
        try:
            qr = parse_gib_qr(qr_payload)
        except GibQrError:
            raise InvalidQrError() from None
        if not 0 < qr.total_minor < MAX_TOTAL_MINOR:
            raise ExtractionRejectedError()

        today = self._today or business_today()
        issues = list(qr.issues)
        qr_date = _plausible(qr.date, today, issues)

        llm: ValidationResult | None = None
        llm_raw: RawReceiptExtraction | None = None
        if masked_text and masked_text.strip():
            if not allow_ai:
                issues.append("text_ignored_no_consent")
            else:
                _check_size(masked_text)
                llm_raw = await self._ask_provider(masked_text, capture_date, "SHARE")
                if llm_raw is None:
                    issues.append("llm_unavailable")
                else:
                    try:
                        llm = validate_receipt(llm_raw, masked_text, today)
                    except ExtractionRejected:
                        issues.append("llm_rejected")
                        llm_raw = None

        extraction, confidence, items = self._compose_qr(qr, qr_date, llm, issues)
        suggestions = await self._suggest(
            user_id,
            extraction.merchant_raw,
            [item.name_raw for item in items],
            seller_id=qr.seller_id,
            allow_ai=allow_ai,
        )
        observation_id = await self._store(
            user_id,
            source=ObservationSource.EINVOICE_QR,
            extraction=extraction,
            total_minor=qr.total_minor,
            items=items,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
            masked_text=masked_text if llm is not None else None,
            llm_output=llm_raw,
            ai_used=llm is not None,
            qr=qr,
        )
        await self._session.commit()
        return ExtractionOutcome(
            observation_id=observation_id,
            extraction=extraction,
            confidence=confidence,
            suggestions=suggestions,
            ai_used=llm is not None,
        )

    @staticmethod
    def _compose_qr(
        qr: GibQr, qr_date: date | None, llm: ValidationResult | None, issues: list[str]
    ) -> tuple[ReceiptExtraction, dict[str, Confidence], list[ParsedItem]]:
        """Header fields (total, date) from the QR; the rest from the model when it ran."""
        confidence: dict[str, Confidence] = {
            "merchant": Confidence.LOW,
            "date": Confidence.HIGH if qr_date else Confidence.LOW,
            "time": Confidence.LOW,
            "total": Confidence.HIGH,
            "payment_method": Confidence.LOW,
            "installment_count": Confidence.HIGH,
            "items": Confidence.LOW,
        }
        merchant = time_ = installment = None
        payment = "UNKNOWN"
        items: list[ParsedItem] = []
        if llm is None:
            issues.extend(["merchant_missing", "no_items"])
        else:
            merchant = llm.extraction.merchant_raw
            time_ = llm.extraction.time
            payment = llm.extraction.payment_method
            installment = llm.extraction.installment_count
            items = llm.items
            for name in ("merchant", "time", "payment_method", "installment_count"):
                confidence[name] = llm.confidence[name]
            # The items are checked against the QR total, the only total we trust here.
            confidence["items"] = _rate_qr_items(items, llm.discount_minor, qr, issues)
            if llm.total_minor is not None and llm.total_minor != qr.total_minor:
                issues.append("llm_total_differs_from_qr")
            if llm.extraction.date is not None and qr_date is not None:
                if llm.extraction.date != qr_date:
                    issues.append("llm_date_differs_from_qr")

        extraction = ReceiptExtraction(
            merchant_raw=merchant,
            date=qr_date,
            time=time_,
            total=Decimal(qr.total_minor).scaleb(-2),
            currency="TRY",
            payment_method=payment,  # type: ignore[arg-type]
            installment_count=installment,
            items=[
                ReceiptItem(
                    name_raw=item.name_raw,
                    quantity=item.quantity,
                    unit_price=None
                    if item.unit_price_minor is None
                    else Decimal(item.unit_price_minor).scaleb(-2),
                    total_price=None
                    if item.total_price_minor is None
                    else Decimal(item.total_price_minor).scaleb(-2),
                )
                for item in items
            ],
        )
        return extraction, {name: confidence[name] for name in FIELDS}, items

    # ---- shared -------------------------------------------------------------------------------

    async def _ask_provider(
        self, masked_text: str, capture_date: date, source: str, *, strict: bool = False
    ) -> RawReceiptExtraction | None:
        """None when the model fails. `strict` (the receipt path, where the AI is the whole
        point): the daily cap is reported as AI_DAILY_LIMIT instead. On the QR path the AI is
        optional and the QR alone still works."""
        hints = ExtractionHints(capture_date=capture_date, source=source)
        try:
            # The SDK call is blocking: keep it off the event loop.
            return await asyncio.to_thread(self._provider.extract_receipt, masked_text, hints)
        except DailyLimitReached:
            logger.warning("extraction_failed", extra={"error_type": "DailyLimitReached"})
            if strict:
                raise AiDailyLimitError() from None
            return None
        except ProviderError as error:
            logger.warning("extraction_failed", extra={"error_type": type(error).__name__})
            return None

    async def _suggest(
        self,
        user_id: uuid.UUID,
        merchant_raw: str | None,
        item_names: list[str],
        *,
        seller_id: str | None = None,
        allow_ai: bool,
    ) -> Suggestions:
        match = await self._normalizer.resolve(user_id, merchant_raw, seller_id=seller_id)
        category = await self._categorizer.categorize(
            user_id,
            match,
            merchant_text=merchant_raw,
            item_names=item_names,
            allow_ai=allow_ai,
        )
        return Suggestions(
            merchant=_merchant_suggestion(match),
            category=CategorySuggestionOut(key=category.key, source=category.source),
        )

    async def _store(
        self,
        user_id: uuid.UUID,
        *,
        source: ObservationSource,
        extraction: ReceiptExtraction,
        total_minor: int | None,
        items: list[ParsedItem],
        confidence: dict[str, Confidence],
        issues: list[str],
        suggestions: Suggestions,
        masked_text: str | None,
        llm_output: RawReceiptExtraction | None,
        ai_used: bool,
        qr: GibQr | None = None,
    ) -> uuid.UUID:
        meta: dict[str, Any] = {"ai_used": ai_used}
        if ai_used:
            meta.update(
                provider=self._provider.name,
                model=self._provider.model,
                prompt_version=self._provider.prompt_version,
            )
        saved: dict[str, Any] = {
            "extraction": extraction.model_dump(mode="json"),
            "issues": issues,
            "meta": meta,
            "suggestions": suggestions.model_dump(mode="json"),
        }
        if llm_output is not None:
            saved["llm_output"] = llm_output.model_dump(mode="json")
        if qr is not None:
            saved["qr"] = qr.clean_fields  # whitelisted invoice fields only

        fingerprint_name = suggestions.merchant.canonical_name or extraction.merchant_raw
        observation = await self._observations.add(
            user_id,
            source=source,
            status=ObservationStatus.PENDING_REVIEW,
            merchant_raw=extraction.merchant_raw,
            amount_minor=total_minor,
            direction=Direction.DEBIT,
            obs_date=extraction.date,
            obs_time=extraction.time,
            installment_count=extraction.installment_count,
            external_id=qr.ettn if qr else None,
            fingerprint=compute_fingerprint(
                source=source.value,
                merchant_raw=fingerprint_name,
                amount_minor=total_minor,
                obs_date=extraction.date,
                obs_time=extraction.time.isoformat() if extraction.time else None,
                external_id=qr.ettn if qr else None,
            ),
            masked_text=masked_text,
            extraction_json=saved,
            field_confidence_json={name: level.value for name, level in confidence.items()},
        )
        for position, item in enumerate(items):
            await self._observations.add_receipt_item(
                user_id,
                observation.id,
                position=position,
                name_raw=item.name_raw,
                quantity=item.quantity if item.quantity is not None else Decimal(1),
                unit_price_minor=item.unit_price_minor,
                total_price_minor=item.total_price_minor,
            )
        return observation.id


def _rate_qr_items(
    items: list[ParsedItem], discount_minor: int, qr: GibQr, issues: list[str]
) -> Confidence:
    """Item lines of an invoice usually add up to the amount BEFORE tax (`malhizmettoplam`), not
    to the amount to pay: either match is fine."""
    attempt: list[str] = []
    level = rate_items(items, discount_minor, qr.total_minor, attempt)
    if level != Confidence.HIGH and qr.goods_total_minor:
        before_tax: list[str] = []
        alternative = rate_items(items, discount_minor, qr.goods_total_minor, before_tax)
        if alternative == Confidence.HIGH:
            return alternative
    issues.extend(attempt)
    return level


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise TextTooLargeError()


def _plausible(day: date | None, today: date, issues: list[str]) -> date | None:
    """The QR date is printed by the seller, but a wrong one is dropped like on a receipt."""
    if day is None:
        return None
    oldest = today.replace(year=today.year - MAX_RECEIPT_AGE_YEARS, day=min(today.day, 28))
    if day > today + timedelta(days=1):
        issues.append("date_in_future")
        return None
    if day < oldest:
        issues.append("date_too_old")
        return None
    return day


def _merchant_suggestion(match: MerchantMatch) -> MerchantSuggestion:
    return MerchantSuggestion(
        match=match.kind,
        merchant_id=match.merchant_id,
        canonical_name=match.canonical_name,
        score=match.score,
    )
