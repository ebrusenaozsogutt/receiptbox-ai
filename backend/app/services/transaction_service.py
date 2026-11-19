"""Reviewing observations and managing transactions (P07).

`confirm` turns a reviewed observation into a NEW transaction (matching with existing ones is P09).
Merchants: a NEW merchant is created here, when the user confirms, with an alias that belongs to
this user only and no default category (DECISIONS P-049); the receipt's own spelling is taught as
an alias too, so the next receipt from the same shop is recognised.
"""

import asyncio
import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ObservationNotPendingError
from app.matching.merchant_normalizer import MerchantMatch, MerchantNormalizer, clean_name
from app.models import Observation, Transaction
from app.models.enums import (
    CategoryKey,
    Direction,
    ObservationSource,
    ObservationStatus,
    PaymentType,
)
from app.repositories.documents import DocumentRepository
from app.repositories.merchants import MerchantRepository
from app.repositories.observations import ObservationRepository
from app.repositories.transactions import TransactionRepository, TransactionRow
from app.schemas.documents import DocumentOut
from app.schemas.transactions import (
    ConfirmRequest,
    EvidenceOut,
    ItemOut,
    ManualTransactionRequest,
    ObservationOut,
    TransactionDetail,
    TransactionList,
    TransactionOut,
    TransactionPatch,
)
from app.services.extraction_service import compute_fingerprint
from app.storage.backend import StorageBackend, StorageError

logger = logging.getLogger("receiptbox.transactions")


class TransactionService:
    def __init__(self, session: AsyncSession, storage: StorageBackend) -> None:
        self._session = session
        self._storage = storage
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
    ) -> TransactionDetail:
        observation = await self._observations.require(user_id, observation_id)
        if observation.status != ObservationStatus.PENDING_REVIEW:
            raise ObservationNotPendingError()

        merchant_id = await self._merchant_for(
            user_id, body.merchant_display, observation.merchant_raw
        )
        transaction = await self._transactions.add(
            user_id,
            merchant_id=merchant_id,
            merchant_display=body.merchant_display,
            category_id=await self._merchants.category_id(body.category_key),
            purchase_date=body.date,
            purchase_time=body.time,
            total_minor=body.total_minor,
            # More than one installment: P10 builds the plan; the flag tells it which ones.
            payment_type=(
                PaymentType.INSTALLMENT
                if (observation.installment_count or 0) > 1
                else PaymentType.SINGLE
            ),
            channel=body.channel,
            note=body.note,
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
        observation.status = ObservationStatus.CONFIRMED
        observation.transaction_id = transaction.id
        await self._session.commit()
        return await self._detail(user_id, transaction.id)

    # ---- transactions -------------------------------------------------------------------------

    async def create_manual(
        self, user_id: uuid.UUID, body: ManualTransactionRequest
    ) -> TransactionDetail:
        merchant_id = await self._merchant_for(user_id, body.merchant_display, None)
        transaction = await self._transactions.add(
            user_id,
            merchant_id=merchant_id,
            merchant_display=body.merchant_display,
            category_id=await self._merchants.category_id(body.category_key),
            purchase_date=body.date,
            purchase_time=body.time,
            total_minor=body.total_minor,
            payment_type=PaymentType.SINGLE,
            channel=body.channel,
            note=body.note,
        )
        await self._observations.add(
            user_id,
            source=ObservationSource.MANUAL,
            status=ObservationStatus.CONFIRMED,
            transaction_id=transaction.id,
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
        await self._session.commit()
        return await self._detail(user_id, transaction.id)

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
