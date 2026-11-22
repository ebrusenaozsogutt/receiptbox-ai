"""Bank screenshot extraction -> pending observations, one per row (spec 5.5, P08).

masked text -> screen check -> provider (rows as text) -> deterministic validation -> merchant and
category suggestions -> fingerprints (duplicates) -> `BANK_SCREENSHOT` observations.

* Only masked text arrives here; the screenshot is never uploaded or stored (spec 15.3).
* Current-account screens are refused (D-014); card-bill payments, loyalty points, headers and
  zero amounts are returned as `skipped` and never saved.
* A row that was imported before (same fingerprint, spec 7.2) is saved as DUPLICATE: uploading the
  same screenshot twice creates no new pending or confirmed row.
* The masked text is kept on the first saved row only (30 days, then nulled at startup).
* Nothing here logs screenshot content.
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.bank_profiles import normalize_bank_hint
from app.ai.bank_validation import (
    SkippedBankRow,
    ValidatedBankRow,
    fold,
    validate_bank_rows,
)
from app.ai.prompts import BANK_ROWS
from app.ai.provider import AIProvider, ProviderError
from app.core.config import Settings
from app.core.errors import (
    BankScreenNotSupportedError,
    ExtractionFailedError,
    TextTooLargeError,
)
from app.matching.merchant_normalizer import MerchantNormalizer
from app.models import Observation
from app.models.enums import ObservationSource, ObservationStatus
from app.repositories.merchants import MerchantRepository
from app.repositories.observations import ObservationRepository
from app.schemas.extraction import CategorySuggestionOut, MerchantSuggestion, Suggestions
from app.schemas.matches import BankRowMatchOut
from app.services.categorization_service import CategorizationService
from app.services.extraction_service import MAX_TEXT_BYTES, compute_fingerprint
from app.services.match_service import MatchService

logger = logging.getLogger("receiptbox.bank")

_ACCOUNT_WORDS = (
    "PARA TRANSFERI",
    "PARA CEKME",
    "FAIZ / KOMISYON",
    "KURUM ODEMESI",
    "KESINTI VE EKLERI",
)


def is_account_screen(masked_text: str) -> bool:
    """A current-account list ("Hesap Hareketleri": ATM, transfers, fees, a balance after every
    row) is not a card transaction list. The title is enough; a screen whose title was not read is
    recognised by its rows."""
    folded = fold(masked_text)
    if "HESAP HAREKETLERI" in folded:
        return True
    balance_lines = sum(1 for line in folded.splitlines() if "[BALANCE]" in line)
    return balance_lines >= 3 and any(word in folded for word in _ACCOUNT_WORDS)


@dataclass(frozen=True)
class BankRowOutcome:
    observation_id: uuid.UUID
    row: ValidatedBankRow
    status: ObservationStatus
    suggestions: Suggestions
    match: BankRowMatchOut | None = None


@dataclass(frozen=True)
class BankOutcome:
    bank_key: str | None
    rows: list[BankRowOutcome]
    skipped: list[SkippedBankRow]


class BankService:
    def __init__(self, session: AsyncSession, provider: AIProvider, settings: Settings) -> None:
        self._session = session
        self._provider = provider
        self._matching = MatchService(session, settings)
        self._observations = ObservationRepository(session)
        merchants = MerchantRepository(session)
        self._normalizer = MerchantNormalizer(merchants)
        self._categorizer = CategorizationService(merchants, provider)

    async def extract(
        self,
        user_id: uuid.UUID,
        *,
        masked_text: str,
        bank_hint: str | None,
        capture_date: date,
    ) -> BankOutcome:
        if len(masked_text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise TextTooLargeError()
        if is_account_screen(masked_text):
            raise BankScreenNotSupportedError()
        bank_key = normalize_bank_hint(bank_hint)

        try:
            # The SDK call is blocking: keep it off the event loop.
            raw_rows = await asyncio.to_thread(
                self._provider.extract_bank_rows, masked_text, bank_key
            )
        except ProviderError as error:
            logger.warning("bank_extraction_failed", extra={"error_type": type(error).__name__})
            raise ExtractionFailedError() from None

        validation = validate_bank_rows(raw_rows, masked_text, bank_key, capture_date)

        prepared: list[tuple[ValidatedBankRow, Suggestions, str]] = []
        seen: dict[str, int] = {}
        for row in validation.rows:
            suggestions = await self._suggest(user_id, row.merchant_raw)
            fingerprint = self._fingerprint(row, suggestions)
            # Two identical rows in ONE screenshot are two purchases: tell them apart by their
            # place, the same way every time the screenshot is read.
            occurrence = seen.get(fingerprint, 0)
            seen[fingerprint] = occurrence + 1
            if occurrence:
                fingerprint = hashlib.sha256(f"{fingerprint}|#{occurrence}".encode()).hexdigest()
            prepared.append((row, suggestions, fingerprint))

        earlier = await self._observations.active_by_fingerprints(
            user_id, ObservationSource.BANK_SCREENSHOT, [item[2] for item in prepared]
        )

        outcomes: list[BankRowOutcome] = []
        text_saved = False
        for row, suggestions, fingerprint in prepared:
            duplicate_of = earlier.get(fingerprint)
            status = (
                ObservationStatus.DUPLICATE if duplicate_of else ObservationStatus.PENDING_REVIEW
            )
            keep_text = not text_saved and duplicate_of is None
            text_saved = text_saved or keep_text
            observation = await self._store(
                user_id,
                row=row,
                status=status,
                suggestions=suggestions,
                fingerprint=fingerprint,
                bank_key=bank_key,
                masked_text=masked_text if keep_text else None,
                duplicate_of=duplicate_of,
            )
            # P09: will this row be merged with a purchase you already have? (nothing is stored)
            match = await self._matching.preview_bank_row(user_id, observation)
            outcomes.append(BankRowOutcome(observation.id, row, status, suggestions, match))
        await self._session.commit()
        return BankOutcome(bank_key=bank_key, rows=outcomes, skipped=validation.skipped)

    # ---- helpers ------------------------------------------------------------------------------

    async def _suggest(self, user_id: uuid.UUID, merchant_raw: str) -> Suggestions:
        match = await self._normalizer.resolve(user_id, merchant_raw)
        # No AI call per row (a screenshot has many): rule, merchant default, else OTHER.
        category = await self._categorizer.categorize(
            user_id, match, merchant_text=merchant_raw, item_names=[], allow_ai=False
        )
        return Suggestions(
            merchant=MerchantSuggestion(
                match=match.kind,
                merchant_id=match.merchant_id,
                canonical_name=match.canonical_name,
                score=match.score,
            ),
            category=CategorySuggestionOut(key=category.key, source=category.source),
        )

    @staticmethod
    def _fingerprint(row: ValidatedBankRow, suggestions: Suggestions) -> str:
        return compute_fingerprint(
            source=ObservationSource.BANK_SCREENSHOT.value,
            merchant_raw=suggestions.merchant.canonical_name or row.merchant_raw,
            amount_minor=row.amount_minor,
            obs_date=row.obs_date,
            obs_time=row.obs_time.isoformat() if row.obs_time else None,
            installment_seq=row.installment_seq,
        )

    async def _store(
        self,
        user_id: uuid.UUID,
        *,
        row: ValidatedBankRow,
        status: ObservationStatus,
        suggestions: Suggestions,
        fingerprint: str,
        bank_key: str | None,
        masked_text: str | None,
        duplicate_of: uuid.UUID | None,
    ) -> Observation:
        saved: dict[str, Any] = {
            "bank_row": {
                "merchant_raw": row.merchant_raw,
                "amount_minor": row.amount_minor,
                "direction": row.direction.value,
                "date_precision": row.date_precision,
                "is_pending": row.is_pending,
            },
            "kind": row.kind,
            "possible_refund": row.kind == "REFUND",
            "issues": row.issues,
            "suggestions": suggestions.model_dump(mode="json"),
            "meta": {
                "provider": self._provider.name,
                "model": self._provider.model,
                "prompt_version": BANK_ROWS,
            },
        }
        if duplicate_of is not None:
            saved["duplicate_of"] = str(duplicate_of)
        observation = await self._observations.add(
            user_id,
            source=ObservationSource.BANK_SCREENSHOT,
            status=status,
            merchant_raw=row.merchant_raw,
            amount_minor=row.amount_minor,
            direction=row.direction,
            obs_date=row.obs_date,
            obs_time=row.obs_time,
            installment_seq=row.installment_seq,
            installment_count=row.installment_count,
            fingerprint=fingerprint,
            masked_text=masked_text,
            extraction_json=saved,
            field_confidence_json={name: level.value for name, level in row.confidence.items()},
            bank_key=bank_key,
        )
        return observation
