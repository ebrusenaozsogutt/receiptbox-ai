"""Reviewing observations and managing transactions (P07, P09).

`confirm` turns a reviewed observation into a transaction. Since P09 the matching engine looks first
(spec 7): the same purchase seen before is MERGED (score >= 95, with an undo), a likely one is
SUGGESTED (the user decides, no transaction exists meanwhile), otherwise a NEW transaction is made.
Merchants: a NEW merchant is created here, when the user confirms, with an alias that belongs to
this user only and no default category (DECISIONS P-049); the receipt's own spelling is taught as
an alias too, so the next receipt from the same shop is recognised.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError, ObservationNotPendingError
from app.matching.engine import MatchOutcome
from app.matching.merchant_normalizer import MerchantMatch, MerchantNormalizer, clean_name
from app.matching.merge import TxFields
from app.models import Observation, Transaction
from app.models.enums import (
    CategoryKey,
    Channel,
    Direction,
    MatchDecisionStatus,
    ObservationSource,
    ObservationStatus,
    PaymentType,
)
from app.repositories.documents import DocumentRepository
from app.repositories.merchants import MerchantRepository
from app.repositories.observations import ObservationRepository
from app.repositories.transactions import TransactionRepository, TransactionRow
from app.schemas.documents import DocumentOut
from app.schemas.matches import MatchOut, MergeOut, SuggestionResponse
from app.schemas.transactions import (
    BatchMerged,
    BatchSkipped,
    ConfirmBatchRequest,
    ConfirmBatchResponse,
    ConfirmRequest,
    EvidenceOut,
    ItemOut,
    ManualTransactionRequest,
    ObservationOut,
    TransactionDetail,
    TransactionList,
    TransactionOut,
    TransactionPatch,
    UnmergeResponse,
)
from app.services.extraction_service import compute_fingerprint
from app.services.match_service import Evaluation, MatchService, without_pending
from app.storage.backend import StorageBackend, StorageError

logger = logging.getLogger("receiptbox.transactions")


class TransactionService:
    def __init__(self, session: AsyncSession, storage: StorageBackend, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._matching = MatchService(session, settings)
        self._transactions = TransactionRepository(session)
        self._observations = ObservationRepository(session)
        self._merchants = MerchantRepository(session)
        self._documents = DocumentRepository(session)
        self._normalizer = MerchantNormalizer(self._merchants)

    # ---- observations (the review queue) ------------------------------------------------------

    async def list_observations(
        self, user_id: uuid.UUID, status: ObservationStatus, *, limit: int, offset: int
    ) -> list[ObservationOut]:
        observations = await self._observations.list_by_status(
            user_id, status, limit=limit, offset=offset
        )
        items = await self._observations.items_of(user_id, [o.id for o in observations])
        by_observation: dict[uuid.UUID, list[ItemOut]] = {}
        for item in items:
            by_observation.setdefault(item.observation_id, []).append(ItemOut.model_validate(item))
        return [_observation_out(o, by_observation.get(o.id, [])) for o in observations]

    async def reject(self, user_id: uuid.UUID, observation_id: uuid.UUID) -> None:
        observation = await self._observations.require(user_id, observation_id)
        if observation.status != ObservationStatus.PENDING_REVIEW:
            raise ObservationNotPendingError()
        observation.status = ObservationStatus.REJECTED
        await self._session.commit()

    async def confirm(
        self, user_id: uuid.UUID, observation_id: uuid.UUID, body: ConfirmRequest
    ) -> TransactionDetail | SuggestionResponse:
        observation = await self._observations.require(user_id, observation_id)
        if observation.status != ObservationStatus.PENDING_REVIEW:
            raise ObservationNotPendingError()

        merchant_id = await self._merchant_for(
            user_id, body.merchant_display, observation.merchant_raw
        )
        if body.remember_category_for_merchant and merchant_id is not None:
            await self._merchants.set_user_rule(user_id, merchant_id, body.category_key)
        await self._observations.replace_items(
            user_id,
            observation.id,
            [
                {
                    "name_raw": item.name_raw,
                    "quantity": item.quantity if item.quantity is not None else 1,
                    "unit_price_minor": item.unit_price_minor,
                    "total_price_minor": item.total_price_minor,
                }
                for item in body.items
            ],
        )
        fields = TxFields(
            merchant_id=merchant_id,
            merchant_display=body.merchant_display,
            category_id=await self._merchants.category_id(body.category_key),
            purchase_date=body.date,
            purchase_time=body.time,
            total_minor=body.total_minor,
            channel=body.channel,
        )
        settled = await self._settle(
            user_id,
            observation,
            fields,
            # More than one installment: P10 builds the plan; the flag tells it which ones.
            payment_type=_payment_type(observation),
            note=body.note,
        )
        await self._session.commit()
        return await self._answer(user_id, settled)

    async def confirm_batch(
        self, user_id: uuid.UUID, body: ConfirmBatchRequest
    ) -> ConfirmBatchResponse:
        """Bank rows -> purchases (P08, P09). Every id must be the caller's (404 otherwise, before
        anything is saved). A DEBIT row is looked up first: the same purchase seen before (a
        receipt) takes the row in as evidence (`merged`), a likely one waits for the user's answer
        (`suggested`), anything else becomes a purchase (`created`). A CREDIT row stays an
        observation flagged "possible refund" (P12). Rows that cannot be saved are `skipped`."""
        observations = [await self._observations.require(user_id, i) for i in body.ids]
        settled_rows: list[tuple[Observation, _Settled]] = []
        skipped: list[BatchSkipped] = []
        for observation in observations:
            edit = body.edits.get(observation.id)
            reason = _batch_skip_reason(observation, edit)
            if reason is not None:
                skipped.append(BatchSkipped(observation_id=observation.id, reason=reason))
                continue
            suggestion = (observation.extraction_json or {}).get("suggestions", {})
            suggested = suggestion.get("category", {}).get("key", CategoryKey.OTHER.value)
            display = (edit.merchant_display if edit else None) or observation.merchant_raw or ""
            category = (edit.category_key if edit else None) or CategoryKey(suggested)
            merchant_id = await self._merchant_for(user_id, display, observation.merchant_raw)
            if edit and edit.remember_category_for_merchant and merchant_id is not None:
                await self._merchants.set_user_rule(user_id, merchant_id, category)
            fields = TxFields(
                merchant_id=merchant_id,
                merchant_display=display,
                category_id=await self._merchants.category_id(category),
                purchase_date=(edit.date if edit and edit.date else observation.obs_date),
                purchase_time=observation.obs_time,
                total_minor=(
                    edit.total_minor if edit and edit.total_minor else observation.amount_minor
                ),
                channel=Channel.UNKNOWN,
            )
            settled = await self._settle(
                user_id,
                observation,
                fields,
                payment_type=_payment_type(observation),
                note=(edit.note if edit else None) or None,
            )
            settled_rows.append((observation, settled))
        await self._session.commit()

        created: list[TransactionDetail] = []
        merged: list[BatchMerged] = []
        suggested_matches: list[MatchOut] = []
        for observation, settled in settled_rows:
            if settled.kind == "SUGGESTED":
                suggested_matches.extend(settled.matches)
                continue
            detail = await self._detail(user_id, settled.transaction_id)  # type: ignore[arg-type]
            if settled.kind == "MERGED" and settled.merge is not None:
                detail = detail.model_copy(update={"outcome": "MERGED", "match": settled.merge})
                merged.append(
                    BatchMerged(
                        observation_id=observation.id, match=settled.merge, transaction=detail
                    )
                )
            else:
                created.append(detail)
        return ConfirmBatchResponse(
            created=created, skipped=skipped, merged=merged, suggested=suggested_matches
        )

    # ---- matching (P09) -----------------------------------------------------------------------

    async def list_matches(
        self, user_id: uuid.UUID, status: MatchDecisionStatus, *, limit: int, offset: int
    ) -> list[MatchOut]:
        return await self._matching.list_matches(user_id, status, limit=limit, offset=offset)

    async def accept_match(self, user_id: uuid.UUID, decision_id: uuid.UUID) -> TransactionDetail:
        """ "Birleştir": the waiting observation joins the suggested purchase."""
        transaction_id, merge = await self._matching.accept(user_id, decision_id)
        await self._session.commit()
        detail = await self._detail(user_id, transaction_id)
        return detail.model_copy(update={"outcome": "MERGED", "match": merge})

    async def reject_match(self, user_id: uuid.UUID, decision_id: uuid.UUID) -> TransactionDetail:
        """ "Ayrı kalsın": the observation becomes its own purchase, as the user reviewed it."""
        observation, fields, pending = await self._matching.reject(user_id, decision_id)
        transaction = await self._create_from(
            user_id,
            fields,
            payment_type=PaymentType(pending.get("payment_type", PaymentType.SINGLE.value)),
            note=pending.get("note"),
        )
        observation.status = ObservationStatus.CONFIRMED
        observation.transaction_id = transaction.id
        observation.extraction_json = without_pending(observation.extraction_json)
        await self._session.commit()
        return await self._detail(user_id, transaction.id)

    async def unmerge(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, observation_id: uuid.UUID
    ) -> UnmergeResponse:
        """ "Ayır" / "Geri al": the two records of a merged purchase become two purchases again."""
        result = await self._matching.unmerge(user_id, transaction_id, observation_id)
        await self._session.commit()
        return UnmergeResponse(
            transaction=await self._detail(user_id, result.transaction_id),
            new_transaction=await self._detail(user_id, result.new_transaction_id),
        )

    async def _settle(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        fields: TxFields,
        *,
        payment_type: PaymentType,
        note: str | None,
    ) -> "_Settled":
        """Spec 7.1: look for the same purchase, then merge, ask, or create."""
        evaluation: Evaluation = await self._matching.evaluate(
            user_id,
            source=observation.source,
            direction=observation.direction,
            amount_minor=fields.total_minor,
            day=fields.purchase_date,
            at=fields.purchase_time,
            merchant_id=fields.merchant_id,
            merchant_name=fields.merchant_display,
            installment_seq=observation.installment_seq,
            installment_count=observation.installment_count,
        )
        outcome = evaluation.result.outcome
        if outcome in (MatchOutcome.NEW, MatchOutcome.INSTALLMENT):
            if outcome == MatchOutcome.NEW:
                await self._matching.record(user_id, observation.id, evaluation)
            transaction = await self._create_from(
                user_id, fields, payment_type=payment_type, note=note
            )
            observation.status = ObservationStatus.CONFIRMED
            observation.transaction_id = transaction.id
            return _Settled("CREATED", transaction.id)

        decisions = await self._matching.record(user_id, observation.id, evaluation)
        best = evaluation.result.strong[0]
        if outcome == MatchOutcome.AUTO:
            transaction = evaluation.candidates[best.transaction_id].transaction
            merge = await self._matching.merge(
                user_id,
                observation,
                transaction,
                fields,
                decisions[best.transaction_id],
                MatchDecisionStatus.AUTO_ACCEPTED,
            )
            return _Settled("MERGED", transaction.id, merge=merge)

        self._matching.hold(observation, fields, payment_type=payment_type, note=note)
        asked = [decisions[candidate.transaction_id] for candidate in evaluation.result.strong]
        return _Settled("SUGGESTED", None, matches=await self._matching.matches_out(user_id, asked))

    async def _answer(
        self, user_id: uuid.UUID, settled: "_Settled"
    ) -> TransactionDetail | SuggestionResponse:
        if settled.kind == "SUGGESTED" or settled.transaction_id is None:
            return SuggestionResponse(matches=settled.matches)
        detail = await self._detail(user_id, settled.transaction_id)
        if settled.kind == "MERGED":
            detail = detail.model_copy(update={"outcome": "MERGED", "match": settled.merge})
        return detail

    async def _create_from(
        self, user_id: uuid.UUID, fields: TxFields, *, payment_type: PaymentType, note: str | None
    ) -> Transaction:
        return await self._transactions.add(
            user_id,
            merchant_id=fields.merchant_id,
            merchant_display=fields.merchant_display,
            category_id=fields.category_id,
            purchase_date=fields.purchase_date,
            purchase_time=fields.purchase_time,
            total_minor=fields.total_minor,
            payment_type=payment_type,
            channel=fields.channel,
            note=note,
        )

    # ---- transactions -------------------------------------------------------------------------

    async def create_manual(
        self, user_id: uuid.UUID, body: ManualTransactionRequest
    ) -> TransactionDetail | SuggestionResponse:
        merchant_id = await self._merchant_for(user_id, body.merchant_display, None)
        # The manual entry is evidence like any other: it may be the same purchase as a bank row.
        observation = await self._observations.add(
            user_id,
            source=ObservationSource.MANUAL,
            status=ObservationStatus.PENDING_REVIEW,
            merchant_raw=body.merchant_display,
            amount_minor=body.total_minor,
            direction=Direction.DEBIT,
            obs_date=body.date,
            obs_time=body.time,
            fingerprint=compute_fingerprint(
                source=ObservationSource.MANUAL.value,
                merchant_raw=body.merchant_display,
                amount_minor=body.total_minor,
                obs_date=body.date,
                obs_time=body.time.isoformat() if body.time else None,
            ),
            extraction_json={"manual": True},
            field_confidence_json={},
        )
        fields = TxFields(
            merchant_id=merchant_id,
            merchant_display=body.merchant_display,
            category_id=await self._merchants.category_id(body.category_key),
            purchase_date=body.date,
            purchase_time=body.time,
            total_minor=body.total_minor,
            channel=body.channel,
        )
        settled = await self._settle(
            user_id, observation, fields, payment_type=PaymentType.SINGLE, note=body.note
        )
        await self._session.commit()
        return await self._answer(user_id, settled)

    async def list(
        self,
        user_id: uuid.UUID,
        *,
        date_from: date | None,
        date_to: date | None,
        category: CategoryKey | None,
        merchant_id: uuid.UUID | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> TransactionList:
        page = await self._transactions.list(
            user_id,
            date_from=date_from,
            date_to=date_to,
            category=category,
            merchant_id=merchant_id,
            search=search,
            limit=limit,
            offset=offset,
        )
        return TransactionList(
            items=[_transaction_out(row) for row in page.rows],
            count=page.count,
            sum_minor=page.sum_minor,
            limit=limit,
            offset=offset,
        )

    async def detail(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> TransactionDetail:
        return await self._detail(user_id, transaction_id)

    async def patch(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, body: TransactionPatch
    ) -> TransactionDetail:
        transaction = await self._require(user_id, transaction_id)
        sent = body.model_fields_set
        if "merchant_display" in sent and body.merchant_display is not None:
            if body.merchant_display != transaction.merchant_display:
                transaction.merchant_id = await self._merchant_for(
                    user_id, body.merchant_display, None
                )
            transaction.merchant_display = body.merchant_display
        if "date" in sent and body.date is not None:
            transaction.purchase_date = body.date
        if "time" in sent:
            transaction.purchase_time = body.time
        if "total_minor" in sent and body.total_minor is not None:
            transaction.total_minor = body.total_minor
        if "category_key" in sent and body.category_key is not None:
            transaction.category_id = await self._merchants.category_id(body.category_key)
        if "channel" in sent and body.channel is not None:
            transaction.channel = body.channel
        if "note" in sent:
            transaction.note = body.note or None
        await self._session.commit()
        return await self._detail(user_id, transaction_id)

    async def delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        """Soft delete (spec 6.3). Its receipt images go with it: they are proof of THIS purchase
        and would otherwise stay invisible in storage. Files that belong to a product stay."""
        await self._require(user_id, transaction_id)
        files = []
        for document in await self._transactions.documents_of(user_id, transaction_id):
            if document.product_id is None:
                files.append(document.storage_key)
                await self._documents.delete(user_id, document.id)
            else:
                document.transaction_id = None
        await self._transactions.soft_delete(user_id, transaction_id)
        await self._session.commit()
        for key in files:
            try:
                await asyncio.to_thread(self._storage.delete, key)
            except StorageError:
                logger.error("document_file_cleanup_failed")

    # ---- helpers ------------------------------------------------------------------------------

    async def _require(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        transaction = await self._transactions.get(user_id, transaction_id)
        if transaction is None:
            raise NotFoundError()  # also for another user's transaction
        return transaction

    async def _merchant_for(
        self, user_id: uuid.UUID, display_name: str, raw_name: str | None
    ) -> uuid.UUID | None:
        """The merchant for what the user confirmed: a known one, or a new one made now."""
        match = await self._normalizer.resolve(user_id, display_name)
        merchant_id = await self._merchant_id(user_id, match)
        # The name the receipt printed may differ from what the user kept: remember it for them.
        if merchant_id is not None and raw_name and raw_name.strip():
            raw_match = await self._normalizer.resolve(user_id, raw_name)
            if raw_match.merchant_id != merchant_id:
                await self._merchants.add_user_alias(
                    user_id, merchant_id, clean_name(raw_name).lookup_keys
                )
        return merchant_id

    async def _merchant_id(self, user_id: uuid.UUID, match: MerchantMatch) -> uuid.UUID | None:
        if match.merchant_id is not None:
            return match.merchant_id
        if match.kind == "NEW" and match.canonical_name:
            created = await self._merchants.create(
                match.canonical_name,
                default_category=None,
                alias_keys=match.alias_keys,
                alias_user_id=user_id,
            )
            return created.id
        return None

    async def _detail(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> TransactionDetail:
        row = await self._transactions.get_row(user_id, transaction_id)
        if row is None:
            raise NotFoundError()
        evidence = await self._transactions.evidence(user_id, transaction_id)
        items = await self._transactions.items_of(user_id, [o.id for o in evidence])
        documents = await self._transactions.documents_of(user_id, transaction_id)
        base = _transaction_out(row)
        return TransactionDetail(
            **base.model_dump(),
            evidence=[
                EvidenceOut(
                    id=o.id,
                    source=o.source,
                    status=o.status,
                    merchant_raw=o.merchant_raw,
                    amount_minor=o.amount_minor,
                    obs_date=o.obs_date,
                    obs_time=o.obs_time,
                    created_at=o.created_at,
                )
                for o in evidence
            ],
            items=[ItemOut.model_validate(item) for item in items],
            documents=[DocumentOut.model_validate(d) for d in documents],
        )


@dataclass(frozen=True)
class _Settled:
    """What happened to one observation that was confirmed: a purchase was CREATED, it was MERGED
    into one the user already had, or a SUGGESTED merge waits for the user's answer."""

    kind: Literal["CREATED", "MERGED", "SUGGESTED"]
    transaction_id: uuid.UUID | None = None
    merge: MergeOut | None = None
    matches: list[MatchOut] = field(default_factory=list)


def _payment_type(observation: Observation) -> PaymentType:
    more_than_one = (observation.installment_count or 0) > 1
    return PaymentType.INSTALLMENT if more_than_one else PaymentType.SINGLE


def _batch_skip_reason(observation: Observation, edit: Any) -> str | None:
    if observation.source != ObservationSource.BANK_SCREENSHOT:
        return "NOT_A_BANK_ROW"
    if observation.status != ObservationStatus.PENDING_REVIEW:
        return "NOT_PENDING"
    if observation.direction == Direction.CREDIT:
        return "POSSIBLE_REFUND"
    if observation.obs_date is None and not (edit and edit.date):
        return "MISSING_DATE"
    if not observation.amount_minor and not (edit and edit.total_minor):
        return "MISSING_AMOUNT"
    if not (observation.merchant_raw or (edit and edit.merchant_display)):
        return "MISSING_MERCHANT"
    return None


def _transaction_out(row: TransactionRow) -> TransactionOut:
    t = row.transaction
    return TransactionOut(
        id=t.id,
        merchant_id=t.merchant_id,
        merchant_display=t.merchant_display,
        category_key=row.category_key,
        purchase_date=t.purchase_date,
        purchase_time=t.purchase_time,
        total_minor=t.total_minor,
        currency=t.currency,
        payment_type=t.payment_type,
        channel=t.channel,
        kind=t.kind,
        is_estimated=t.is_estimated,
        note=t.note,
        document_count=row.document_count,
        created_at=t.created_at,
    )


def _observation_out(observation: Observation, items: list[ItemOut]) -> ObservationOut:
    saved: dict[str, Any] = observation.extraction_json or {}
    return ObservationOut(
        id=observation.id,
        source=observation.source,
        status=observation.status,
        merchant_raw=observation.merchant_raw,
        amount_minor=observation.amount_minor,
        obs_date=observation.obs_date,
        obs_time=observation.obs_time,
        installment_count=observation.installment_count,
        extraction=saved.get("extraction"),
        suggestions=saved.get("suggestions"),
        confidence=observation.field_confidence_json or {},
        items=items,
        transaction_id=observation.transaction_id,
        created_at=observation.created_at,
    )
