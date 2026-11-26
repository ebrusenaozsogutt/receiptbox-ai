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
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.bank_profiles import profile_for
from app.core.config import Settings
from app.core.errors import NotARefundRowError, NotFoundError, ObservationNotPendingError
from app.matching.engine import MatchOutcome
from app.matching.installment_matcher import InstallmentOutcome, InstallmentRow
from app.matching.merchant_normalizer import MerchantMatch, MerchantNormalizer, clean_name
from app.matching.merge import TxFields
from app.models import Observation, Transaction
from app.models.enums import (
    CategoryKey,
    Channel,
    Direction,
    MatchDecisionStatus,
    MatchType,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    TransactionKind,
)
from app.repositories.documents import DocumentRepository
from app.repositories.merchants import MerchantRepository
from app.repositories.observations import ObservationRepository
from app.repositories.products import ProductRepository
from app.repositories.transactions import TransactionRepository, TransactionRow
from app.schemas.documents import DocumentOut
from app.schemas.installments import PlanIn, PlanPatch
from app.schemas.matches import MatchOut, MergeOut, SuggestionResponse
from app.schemas.products import (
    RefundIn,
    RefundLinkIn,
    RefundSuggestionList,
    RefundSuggestionOut,
)
from app.schemas.transactions import (
    BatchLinked,
    BatchMerged,
    BatchSkipped,
    ConfirmBatchRequest,
    ConfirmBatchResponse,
    ConfirmRequest,
    EvidenceOut,
    ItemOut,
    ManualTransactionRequest,
    ObservationOut,
    ProductBrief,
    RefundEntry,
    TransactionDetail,
    TransactionList,
    TransactionOut,
    TransactionPatch,
    UnmergeResponse,
)
from app.services.budget_service import BudgetService
from app.services.extraction_service import BUSINESS_TIMEZONE, compute_fingerprint
from app.services.installment_service import InstallmentService, RowContext, capture_date_of
from app.services.match_service import Evaluation, MatchService, without_pending
from app.services.product_service import ProductService
from app.services.refund_service import RefundService
from app.services.reminder_service import ReminderService
from app.storage.backend import StorageBackend, StorageError

logger = logging.getLogger("receiptbox.transactions")


def business_today() -> date:
    """Today in the business timezone (Europe/Istanbul)."""
    return datetime.now(BUSINESS_TIMEZONE).date()


class TransactionService:
    def __init__(self, session: AsyncSession, storage: StorageBackend, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._matching = MatchService(session, settings)
        self._installments = InstallmentService(session)
        self._transactions = TransactionRepository(session)
        self._observations = ObservationRepository(session)
        self._merchants = MerchantRepository(session)
        self._documents = DocumentRepository(session)
        self._normalizer = MerchantNormalizer(self._merchants)
        self._settings = settings
        self._products = ProductRepository(session)
        self._refunds = RefundService(session)

    # ---- observations (the review queue) ------------------------------------------------------

    async def _commit(self, user_id: uuid.UUID) -> None:
        """Commit, after creating the budget reminders the change may have reached (P11) and
        recomputing the deadline reminders (P13: installment plans created, changed or cancelled,
        refunds that return a product, purchases deleted). Every write of this service ends
        here, so both happen in the same transaction."""
        await BudgetService(self._session).check_reminders(user_id)
        await ReminderService(self._session).sync(user_id)
        await self._session.commit()

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
        await self._commit(user_id)

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
        # "Taksitli": what the user chose on the review form. An older client that does not send
        # the field keeps what the reading found.
        count = (
            body.installment_count
            if "installment_count" in body.model_fields_set
            else _reading_count(observation)
        )
        settled = await self._settle(
            user_id,
            observation,
            fields,
            payment_type=PaymentType.INSTALLMENT if count else PaymentType.SINGLE,
            note=body.note,
            installment_count=count,
        )
        await self._commit(user_id)
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
            note = (edit.note if edit else None) or None
            if observation.installment_seq is not None and observation.installment_count:
                # `k/n`: one payment of a plan (spec 8.2), never a purchase of its own
                settled = await self._settle_installment_row(user_id, observation, fields, note)
            else:
                count = _reading_count(observation)
                settled = await self._settle(
                    user_id,
                    observation,
                    fields,
                    payment_type=PaymentType.INSTALLMENT if count else PaymentType.SINGLE,
                    note=note,
                    installment_count=count,
                )
            settled_rows.append((observation, settled))
        await self._commit(user_id)

        created: list[TransactionDetail] = []
        merged: list[BatchMerged] = []
        linked: list[BatchLinked] = []
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
            elif settled.kind == "LINKED":
                detail = detail.model_copy(update={"outcome": "LINKED"})
                linked.append(
                    BatchLinked(
                        observation_id=observation.id,
                        seq=settled.seq or 0,
                        count=settled.count or 0,
                        transaction=detail,
                    )
                )
            else:
                created.append(detail)  # a new purchase, also an ESTIMATED one
        return ConfirmBatchResponse(
            created=created,
            skipped=skipped,
            merged=merged,
            linked=linked,
            suggested=suggested_matches,
        )

    # ---- matching (P09) -----------------------------------------------------------------------

    async def list_matches(
        self, user_id: uuid.UUID, status: MatchDecisionStatus, *, limit: int, offset: int
    ) -> list[MatchOut]:
        return await self._matching.list_matches(user_id, status, limit=limit, offset=offset)

    async def accept_match(self, user_id: uuid.UUID, decision_id: uuid.UUID) -> TransactionDetail:
        """ "Birleştir": the waiting observation joins the suggested purchase (or, for an
        installment suggestion, becomes one of its payments)."""
        decision, observation = await self._matching.open_decision(user_id, decision_id)
        if decision.match_type == MatchType.INSTALLMENT:
            return await self._accept_installment(user_id, decision, observation)
        pending = (observation.extraction_json or {}).get("pending", {})
        count = pending.get("installment_count")
        transaction_id, merge = await self._matching.accept(user_id, decision_id)
        transaction = await self._transactions.get(user_id, transaction_id)
        if transaction is not None:
            await self._after_merge(user_id, transaction, observation, count)
        await self._commit(user_id)
        detail = await self._detail(user_id, transaction_id)
        return detail.model_copy(update={"outcome": "MERGED", "match": merge})

    async def _accept_installment(
        self, user_id: uuid.UUID, decision: Any, observation: Observation
    ) -> TransactionDetail:
        features = decision.features_json or {}
        transaction = await self._installments.accept_installment(
            user_id,
            observation,
            decision.transaction_id,
            seq=int(features["seq"]),
            count=int(features["count"]),
        )
        decision.decision = MatchDecisionStatus.ACCEPTED
        decision.decided_at = datetime.now().astimezone()
        decision.installment_payment_id = observation.installment_payment_id
        await self._matching.close_pending(user_id, observation.id)
        observation.extraction_json = without_pending(observation.extraction_json)
        await self._commit(user_id)
        detail = await self._detail(user_id, transaction.id)
        return detail.model_copy(update={"outcome": "LINKED"})

    async def _after_merge(
        self,
        user_id: uuid.UUID,
        transaction: Transaction,
        observation: Observation,
        count: int | None,
    ) -> None:
        """A record was merged into a purchase: when it was only an estimate and the record is a
        receipt or an e-invoice, it is real now (P10)."""
        if transaction.is_estimated or count:
            await self._installments.on_receipt_merged(
                user_id,
                transaction,
                receipt_count=count,
                clears_estimate=observation.source
                in (ObservationSource.RECEIPT, ObservationSource.EINVOICE_QR),
            )

    async def reject_match(self, user_id: uuid.UUID, decision_id: uuid.UUID) -> TransactionDetail:
        """ "Ayrı kalsın": the observation becomes its own purchase, as the user reviewed it."""
        observation, fields, pending = await self._matching.reject(user_id, decision_id)
        if "installment" in pending:
            # an installment row none of the plans was chosen for: an estimated purchase
            transaction = await self._create_estimated(
                user_id, observation, fields, pending.get("note")
            )
            observation.extraction_json = without_pending(observation.extraction_json)
            await self._commit(user_id)
            return await self._detail(user_id, transaction.id)
        transaction = await self._create_from(
            user_id,
            fields,
            payment_type=PaymentType(pending.get("payment_type", PaymentType.SINGLE.value)),
            note=pending.get("note"),
        )
        if pending.get("installment_count"):
            await self._installments.create_plan(
                transaction, count=int(pending["installment_count"])
            )
        observation.status = ObservationStatus.CONFIRMED
        observation.transaction_id = transaction.id
        observation.extraction_json = without_pending(observation.extraction_json)
        await self._commit(user_id)
        return await self._detail(user_id, transaction.id)

    async def unmerge(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, observation_id: uuid.UUID
    ) -> UnmergeResponse:
        """ "Ayır" / "Geri al": the two records of a merged purchase become two purchases again."""
        result = await self._matching.unmerge(user_id, transaction_id, observation_id)
        await self._commit(user_id)
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
        installment_count: int | None = None,
    ) -> "_Settled":
        """Spec 7.1: look for the same purchase, then merge, ask, or create. P10: a purchase of
        `installment_count` installments gets its plan; a bank row that may be one payment of an
        earlier purchase is asked about (spec 8.3)."""
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
                asked = await self._ask_if_a_payment(
                    user_id, observation, fields, payment_type, note, installment_count
                )
                if asked is not None:
                    return asked
            transaction = await self._create_from(
                user_id, fields, payment_type=payment_type, note=note
            )
            if installment_count:
                await self._installments.create_plan(transaction, count=installment_count)
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
            await self._after_merge(user_id, transaction, observation, installment_count)
            return _Settled("MERGED", transaction.id, merge=merge)

        self._matching.hold(
            observation,
            fields,
            payment_type=payment_type,
            note=note,
            extra={"installment_count": installment_count} if installment_count else None,
        )
        asked = [decisions[candidate.transaction_id] for candidate in evaluation.result.strong]
        return _Settled("SUGGESTED", None, matches=await self._matching.matches_out(user_id, asked))

    # ---- installments (P10) -------------------------------------------------------------------

    def _today(self) -> date:
        return business_today()

    def _context(self, observation: Observation, fields: TxFields) -> RowContext:
        """The bank row for the matcher, with what the user may have edited (amount, date)."""
        return RowContext(
            InstallmentRow(
                merchant_id=None,
                merchant_name=fields.merchant_display,
                amount_minor=fields.total_minor,
                seq=observation.installment_seq,
                count=observation.installment_count,
                row_date=fields.purchase_date,
                capture_date=capture_date_of(observation, self._today()),
            ),
            fields.merchant_id,
        )

    async def _settle_installment_row(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        fields: TxFields,
        note: str | None,
    ) -> "_Settled":
        """A bank row `k/n` (spec 8.2): payment k of a plan that fits (OBSERVED, the earlier ones
        INFERRED, no spending added), else an ESTIMATED purchase with a plan. Several plans that
        fit equally are asked about, never guessed."""
        context = self._context(observation, fields)
        match = await self._installments.match_row(user_id, context)
        decisions = await self._installments.record_row_candidates(user_id, observation.id, match)
        seq, count = observation.installment_seq or 0, observation.installment_count or 0
        if match.outcome == InstallmentOutcome.LINK and match.best is not None:
            plan = await self._installments.plan_by_id(user_id, match.best.plan.plan_id)
            payment = await self._installments.link_payment(observation, plan, seq)
            decisions[match.best.plan.transaction_id].installment_payment_id = payment.id
            return _Settled("LINKED", plan.transaction_id, seq=seq, count=count)
        if match.outcome == InstallmentOutcome.AMBIGUOUS:
            self._matching.hold(
                observation,
                fields,
                payment_type=PaymentType.INSTALLMENT,
                note=note,
                extra={"installment": {"seq": seq, "count": count}},
            )
            asked = [decisions[s.plan.transaction_id] for s in match.eligible]
            return _Settled(
                "SUGGESTED", None, matches=await self._matching.matches_out(user_id, asked)
            )
        transaction = await self._create_estimated(user_id, observation, fields, note)
        return _Settled("ESTIMATED", transaction.id, seq=seq, count=count)

    async def _create_estimated(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        fields: TxFields,
        note: str | None,
    ) -> Transaction:
        """Spec 8.2 step 3: total = n x amount, the date about (k-1) months before the row, a plan
        with the earlier payments INFERRED and this one OBSERVED. A receipt that comes later is
        matched with it by the 1:1 engine and clears the estimate."""
        context = self._context(observation, fields)
        carries_date = profile_for(observation.bank_key).installment_rows_carry_purchase_date
        estimate = self._installments.estimate(context, row_date_is_purchase_date=carries_date)
        transaction = await self._transactions.add(
            user_id,
            merchant_id=fields.merchant_id,
            merchant_display=fields.merchant_display,
            category_id=fields.category_id,
            purchase_date=estimate.purchase_date,
            purchase_time=None,
            total_minor=estimate.total_minor,
            payment_type=PaymentType.INSTALLMENT,
            channel=Channel.UNKNOWN,
            note=note,
            is_estimated=True,
        )
        plan = await self._installments.create_plan(
            transaction,
            count=estimate.count,
            first_due_month=estimate.first_due_month,
            inferred_before=estimate.seq,
        )
        await self._installments.link_payment(observation, plan, estimate.seq)
        return transaction

    async def _ask_if_a_payment(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        fields: TxFields,
        payment_type: PaymentType,
        note: str | None,
        installment_count: int | None,
    ) -> "_Settled | None":
        """Spec 8.3: a bank row without a marker whose amount is about total/n of an earlier
        purchase of the same shop. Only a suggestion, never automatic."""
        if (
            observation.source != ObservationSource.BANK_SCREENSHOT
            or observation.installment_seq is not None
            or installment_count
        ):
            return None
        suggestions = await self._installments.suggest_for_row(
            user_id, self._context(observation, fields)
        )
        if not suggestions:
            return None
        decisions = await self._installments.record_suggestions(
            user_id, observation.id, suggestions
        )
        self._matching.hold(observation, fields, payment_type=payment_type, note=note)
        return _Settled(
            "SUGGESTED", None, matches=await self._matching.matches_out(user_id, decisions)
        )

    async def put_plan(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, body: PlanIn
    ) -> TransactionDetail:
        """ "Taksitli": create the plan of a purchase (replace it while no bank row is on it)."""
        transaction = await self._require(user_id, transaction_id)
        await self._installments.replace_plan(
            user_id,
            transaction,
            count=body.count,
            first_due_month=body.first_due_month,
            total_payable_minor=body.total_payable_minor,
        )
        await self._commit(user_id)
        return await self._detail(user_id, transaction_id)

    async def patch_plan(
        self, user_id: uuid.UUID, plan_id: uuid.UUID, body: PlanPatch
    ) -> TransactionDetail:
        transaction = await self._installments.patch_plan(
            user_id,
            plan_id,
            status=body.status,
            first_due_month=body.first_due_month,
            total_payable_minor=body.total_payable_minor,
            sent=set(body.model_fields_set),
        )
        await self._commit(user_id)
        return await self._detail(user_id, transaction.id)

    async def schedule(self, user_id: uuid.UUID, *, from_month: date, to_month: date):  # noqa: ANN201
        today = self._today()
        await self._installments.complete_finished_plans(today)
        result = await self._installments.schedule(
            user_id, from_month=from_month, to_month=to_month, today=today
        )
        await self._commit(user_id)
        return result

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
            user_id,
            observation,
            fields,
            payment_type=PaymentType.INSTALLMENT if body.installment_count else PaymentType.SINGLE,
            note=body.note,
            installment_count=body.installment_count,
        )
        await self._commit(user_id)
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
            old_total = transaction.total_minor
            transaction.total_minor = body.total_minor
            await self._installments.follow_total(user_id, transaction, old_total)
        if "category_key" in sent and body.category_key is not None:
            transaction.category_id = await self._merchants.category_id(body.category_key)
        if "channel" in sent and body.channel is not None:
            transaction.channel = body.channel
        if "note" in sent:
            transaction.note = body.note or None
        await self._commit(user_id)
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
        await self._commit(user_id)
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
                    installment_seq=o.installment_seq,
                    installment_count=o.installment_count,
                    is_installment_payment=o.installment_payment_id is not None,
                )
                for o in evidence
            ],
            items=[ItemOut.model_validate(item) for item in items],
            documents=[DocumentOut.model_validate(d) for d in documents],
            plan=await self._installments.plan_out(user_id, transaction_id),
            **await self._refund_and_product_fields(user_id, row.transaction),
        )

    async def _refund_and_product_fields(
        self, user_id: uuid.UUID, transaction: Transaction
    ) -> dict[str, Any]:
        """P12: the refunds, what is left to refund, the products and the product suggestions of a
        purchase (empty for a refund)."""
        if transaction.kind != TransactionKind.PURCHASE:
            return {}
        refunds = await self._products.refunds_of(user_id, transaction.id)
        products = await self._products.of_transaction(user_id, transaction.id)
        suggestions = await ProductService(self._session, self._settings).suggestions(
            user_id, transaction.id
        )
        return {
            "refunds": [
                RefundEntry(id=r.id, date=r.purchase_date, amount_minor=r.total_minor)
                for r in refunds
            ],
            "refundable_minor": max(
                0, transaction.total_minor - sum(r.total_minor for r in refunds)
            ),
            "products": [ProductBrief(id=p.id, name=p.name, status=p.status) for p in products],
            "product_suggestions": suggestions.items,
        }

    # ---- refunds (P12) ----------------------------------------------------------------------

    async def refund(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, body: RefundIn
    ) -> TransactionDetail:
        """Spec 9: "İade edildi", full or partial. Answers the purchase with its refunds."""
        purchase = await self._refunds.purchase(user_id, transaction_id)
        await self._refunds.refund(
            user_id,
            purchase,
            amount_minor=body.amount_minor,
            day=body.date,
            today=business_today(),
            product_id=body.product_id,
        )
        await self._commit(user_id)
        return await self._detail(user_id, transaction_id)

    async def refund_suggestions(self, user_id: uuid.UUID) -> RefundSuggestionList:
        """The pending bank CREDIT rows with the purchases they may refund (suggestions only)."""
        items = []
        for observation in await self._refunds.pending_credit_rows(user_id):
            if observation.amount_minor is None or observation.obs_date is None:
                continue
            items.append(
                RefundSuggestionOut(
                    observation_id=observation.id,
                    merchant_raw=observation.merchant_raw,
                    amount_minor=observation.amount_minor,
                    obs_date=observation.obs_date,
                    candidates=await self._refunds.candidates(user_id, observation),
                )
            )
        return RefundSuggestionList(items=items)

    async def link_refund(
        self, user_id: uuid.UUID, observation_id: uuid.UUID, body: RefundLinkIn
    ) -> TransactionDetail:
        """The user says: this bank CREDIT row is a refund of that purchase. The row becomes the
        evidence of a REFUND transaction (amount and date from the bank)."""
        observation = await self._observations.require(user_id, observation_id)
        if observation.status != ObservationStatus.PENDING_REVIEW:
            raise ObservationNotPendingError()
        if (
            observation.source != ObservationSource.BANK_SCREENSHOT
            or observation.direction != Direction.CREDIT
            or not observation.amount_minor
            or observation.obs_date is None
        ):
            raise NotARefundRowError()
        purchase = await self._refunds.purchase(user_id, body.transaction_id)
        refund = await self._refunds.refund(
            user_id,
            purchase,
            amount_minor=observation.amount_minor,
            day=observation.obs_date,
            today=max(business_today(), observation.obs_date),
        )
        observation.transaction_id = refund.id
        observation.status = ObservationStatus.CONFIRMED
        await self._commit(user_id)
        return await self._detail(user_id, purchase.id)


@dataclass(frozen=True)
class _Settled:
    """What happened to one observation that was confirmed: a purchase was CREATED, it was MERGED
    into one the user already had, or a SUGGESTED merge waits for the user's answer."""

    kind: Literal["CREATED", "MERGED", "SUGGESTED", "LINKED", "ESTIMATED"]
    transaction_id: uuid.UUID | None = None
    merge: MergeOut | None = None
    matches: list[MatchOut] = field(default_factory=list)
    seq: int | None = None  # LINKED / ESTIMATED: which payment the bank row became
    count: int | None = None


def _reading_count(observation: Observation) -> int | None:
    """The number of installments the reading found on a receipt, a slip or a bank row that shows
    the whole total ("3 taksit"), or None."""
    count = observation.installment_count or 0
    return count if count > 1 else None


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
        refund_of_id=t.refund_of_id,
        refunded_minor=row.refunded_minor,
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
