"""Matching: evaluate, record, merge, answer a suggestion, unmerge (spec 7, P09).

The scoring is pure (`app/matching/features.py`, `engine.py`); this service is the part that talks
to the database. Rules it keeps:

* every query filters by `user_id` (another user's decision, observation or purchase is a 404);
* every candidate from `MATCH_RECORD_MIN` up is stored in `match_decisions` with its
  `features_json` (P15 trains on them): the chosen one as AUTO_ACCEPTED / PENDING, the others as
  REJECTED (the system's "not this one"). A new evaluation replaces the still PENDING decisions of
  the same observation; decided ones stay;
* merging attaches the observation to the transaction; the higher source wins the canonical fields
  (QR > receipt > bank > manual), the lower source stays evidence; the snapshot written with the
  decision lets "Ayır" restore two transactions (spec 7.5);
* a suggestion creates NO transaction: the reviewed fields wait in `extraction_json["pending"]`
  until the user accepts (merge) or rejects (a new transaction is made from them);
* nothing here logs merchant names or amounts.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    MatchNotAvailableError,
    MatchNotPendingError,
    NotFoundError,
    NotMergedError,
)
from app.matching.candidates import Candidate, find_candidates
from app.matching.engine import (
    MatchOutcome,
    MatchResult,
    ScoredCandidate,
    Thresholds,
    decide,
    defers_to_installments,
    source_rank,
)
from app.matching.features import MatchSide, score_pair
from app.matching.merge import TxFields, apply_fields, revert_fields
from app.models import MatchDecision, Observation, Transaction
from app.models.enums import (
    Direction,
    MatchDecisionStatus,
    MatchType,
    ObservationSource,
    ObservationStatus,
    PaymentType,
)
from app.repositories.matches import MatchDecisionRepository
from app.repositories.observations import ObservationRepository
from app.repositories.transactions import TransactionRepository
from app.schemas.matches import (
    BankRowMatchOut,
    MatchObservationOut,
    MatchOut,
    MatchTransactionOut,
    MergeOut,
)

PENDING_KEY = "pending"  # extraction_json key: the reviewed fields of an observation that waits


@dataclass(frozen=True)
class Evaluation:
    result: MatchResult
    candidates: dict[uuid.UUID, Candidate]


@dataclass(frozen=True)
class Unmerged:
    transaction_id: uuid.UUID
    new_transaction_id: uuid.UUID


def _now() -> datetime:
    return datetime.now().astimezone()


def side_of(transaction: Transaction) -> MatchSide:
    return MatchSide(
        amount_minor=transaction.total_minor,
        day=transaction.purchase_date,
        at=transaction.purchase_time,
        merchant_id=transaction.merchant_id,
        merchant_name=transaction.merchant_display,
    )


class MatchService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._thresholds = Thresholds.from_settings(settings)
        self._decisions = MatchDecisionRepository(session)
        self._observations = ObservationRepository(session)
        self._transactions = TransactionRepository(session)

    # ---- evaluate -----------------------------------------------------------------------------

    async def evaluate(
        self,
        user_id: uuid.UUID,
        *,
        source: ObservationSource,
        direction: Direction,
        amount_minor: int | None,
        day: date | None,
        at: time | None,
        merchant_id: uuid.UUID | None,
        merchant_name: str,
        installment_seq: int | None,
        installment_count: int | None,
        exclude_transaction_id: uuid.UUID | None = None,
    ) -> Evaluation:
        """Spec 7.1 steps 2-5. Writes nothing."""
        if direction != Direction.DEBIT or not amount_minor or day is None:
            return Evaluation(MatchResult(MatchOutcome.NEW), {})  # credits: refunds are P12
        if defers_to_installments(installment_seq, installment_count):
            return Evaluation(MatchResult(MatchOutcome.INSTALLMENT), {})  # P10 hook

        found = await find_candidates(
            self._session,
            user_id,
            source=source,
            amount_minor=amount_minor,
            day=day,
            exclude_transaction_id=exclude_transaction_id,
        )
        new = MatchSide(
            amount_minor=amount_minor,
            day=day,
            at=at,
            merchant_id=merchant_id,
            merchant_name=merchant_name,
        )
        scored = [
            ScoredCandidate(
                candidate.transaction.id,
                score_pair(
                    new,
                    side_of(candidate.transaction),
                    source_pair=f"{source.value}|{'+'.join(s.value for s in candidate.sources)}",
                ),
            )
            for candidate in found
        ]
        return Evaluation(decide(scored, self._thresholds), {c.transaction.id: c for c in found})

    # ---- record -------------------------------------------------------------------------------

    async def record(
        self, user_id: uuid.UUID, observation_id: uuid.UUID, evaluation: Evaluation
    ) -> dict[uuid.UUID, MatchDecision]:
        """Store every candidate from `record_min` up (transaction id -> its decision row)."""
        await self._decisions.delete_pending_for_observation(user_id, observation_id)
        result = evaluation.result
        chosen = result.strong[0].transaction_id if result.outcome == MatchOutcome.AUTO else None
        strong_ids = {c.transaction_id for c in result.strong}
        saved: dict[uuid.UUID, MatchDecision] = {}
        for candidate in result.candidates:
            if candidate.transaction_id == chosen:
                status = MatchDecisionStatus.AUTO_ACCEPTED
            elif result.outcome == MatchOutcome.SUGGEST and candidate.transaction_id in strong_ids:
                status = MatchDecisionStatus.PENDING
            else:
                status = MatchDecisionStatus.REJECTED  # below the suggest threshold: not this one
            saved[candidate.transaction_id] = await self._decisions.add(
                user_id,
                observation_id=observation_id,
                transaction_id=candidate.transaction_id,
                match_type=MatchType.DUPLICATE,
                score=Decimal(str(candidate.score)),
                features_json=candidate.features.as_json(),
                decision=status,
                decided_at=None if status == MatchDecisionStatus.PENDING else _now(),
            )
        return saved

    # ---- merge --------------------------------------------------------------------------------

    async def merge(
        self,
        user_id: uuid.UUID,
        observation: Observation,
        transaction: Transaction,
        incoming: TxFields,
        decision: MatchDecision,
        status: MatchDecisionStatus,
    ) -> MergeOut:
        """Attach the observation to the purchase. The higher source wins the fields (spec 7.5)."""
        attached = await self._transactions.evidence(user_id, transaction.id)
        if any(
            o.source == observation.source and o.status == ObservationStatus.CONFIRMED
            for o in attached
        ):
            raise MatchNotAvailableError()  # a purchase has at most one record per source (6.3)

        before = TxFields.of(transaction)
        strongest = max((source_rank(o.source) for o in attached), default=0)
        if source_rank(observation.source) > strongest:
            apply_fields(transaction, incoming, keep_channel_if_unknown=True)
        after = TxFields.of(transaction)

        observation.status = ObservationStatus.CONFIRMED
        observation.transaction_id = transaction.id
        observation.extraction_json = without_pending(observation.extraction_json)
        decision.transaction_id = transaction.id
        decision.decision = status
        decision.decided_at = _now()
        decision.merge_snapshot = {
            "before": before.to_json(),
            "incoming": incoming.to_json(),
            "after": after.to_json(),
        }
        await self._session.flush()
        return MergeOut(
            decision_id=decision.id,
            decision=status,
            score=float(decision.score) if decision.score is not None else None,
            observation_id=observation.id,
        )

    def hold(
        self,
        observation: Observation,
        fields: TxFields,
        *,
        payment_type: PaymentType,
        note: str | None,
    ) -> None:
        """Keep what the user reviewed while a suggestion waits (no transaction yet)."""
        observation.extraction_json = {
            **(observation.extraction_json or {}),
            PENDING_KEY: {
                **fields.to_json(),
                "payment_type": payment_type.value,
                "note": note,
            },
        }

    # ---- answering a suggestion ---------------------------------------------------------------

    async def accept(
        self, user_id: uuid.UUID, decision_id: uuid.UUID
    ) -> tuple[uuid.UUID, MergeOut]:
        decision, observation = await self._open_decision(user_id, decision_id)
        transaction = (
            await self._transactions.get(user_id, decision.transaction_id)
            if decision.transaction_id
            else None
        )
        if transaction is None:
            raise MatchNotAvailableError()
        incoming = TxFields.from_json(_pending_of(observation))
        merged = await self.merge(
            user_id, observation, transaction, incoming, decision, MatchDecisionStatus.ACCEPTED
        )
        for other in await self._decisions.pending_for_observation(user_id, observation.id):
            other.decision = MatchDecisionStatus.REJECTED
            other.decided_at = _now()
        return transaction.id, merged

    async def reject(
        self, user_id: uuid.UUID, decision_id: uuid.UUID
    ) -> tuple[Observation, TxFields, dict[str, Any]]:
        """The user says "ayrı kalsın": every open suggestion of the observation is closed and the
        caller creates the purchase from the reviewed fields (returned here)."""
        _, observation = await self._open_decision(user_id, decision_id)
        for other in await self._decisions.pending_for_observation(user_id, observation.id):
            other.decision = MatchDecisionStatus.REJECTED
            other.decided_at = _now()
        pending = _pending_of(observation)
        return observation, TxFields.from_json(pending), pending

    async def _open_decision(
        self, user_id: uuid.UUID, decision_id: uuid.UUID
    ) -> tuple[MatchDecision, Observation]:
        decision = await self._decisions.require(user_id, decision_id)
        if decision.decision != MatchDecisionStatus.PENDING:
            raise MatchNotPendingError()
        observation = await self._observations.require(user_id, decision.observation_id)
        if observation.status != ObservationStatus.PENDING_REVIEW or PENDING_KEY not in (
            observation.extraction_json or {}
        ):
            raise MatchNotPendingError()
        return decision, observation

    # ---- unmerge ------------------------------------------------------------------------------

    async def unmerge(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, observation_id: uuid.UUID
    ) -> Unmerged:
        """ "Ayır": two records of one purchase become two purchases again (spec 7.5)."""
        transaction = await self._transactions.get(user_id, transaction_id)
        if transaction is None:
            raise NotFoundError()
        evidence = await self._transactions.evidence(user_id, transaction_id)
        leaving = next((o for o in evidence if o.id == observation_id), None)
        if leaving is None:
            raise NotFoundError()
        merges = await self._decisions.active_merges_of(user_id, transaction_id)
        if len(evidence) != 2 or not merges:
            raise NotMergedError()
        decision = merges[0]
        if decision.observation_id not in {o.id for o in evidence} or not decision.merge_snapshot:
            raise NotMergedError()

        snapshot = decision.merge_snapshot
        before = TxFields.from_json(snapshot["before"])
        incoming = TxFields.from_json(snapshot["incoming"])
        after = TxFields.from_json(snapshot["after"])
        leaving_is_the_merged_one = leaving.id == decision.observation_id
        leaving_fields = incoming if leaving_is_the_merged_one else before
        remaining_fields = before if leaving_is_the_merged_one else incoming

        created = await self._transactions.add(
            user_id,
            merchant_id=leaving_fields.merchant_id,
            merchant_display=leaving_fields.merchant_display,
            category_id=leaving_fields.category_id,
            purchase_date=leaving_fields.purchase_date,
            purchase_time=leaving_fields.purchase_time,
            total_minor=leaving_fields.total_minor,
            payment_type=PaymentType.SINGLE,
            channel=leaving_fields.channel,
            note=None,
        )
        leaving.transaction_id = created.id
        revert_fields(transaction, after, remaining_fields)
        decision.decision = MatchDecisionStatus.UNDONE
        decision.decided_at = _now()
        await self._session.flush()
        return Unmerged(transaction_id=transaction.id, new_transaction_id=created.id)

    # ---- read ---------------------------------------------------------------------------------

    async def list_matches(
        self, user_id: uuid.UUID, status: MatchDecisionStatus, *, limit: int, offset: int
    ) -> list[MatchOut]:
        decisions = await self._decisions.with_status(user_id, status, limit=limit, offset=offset)
        return await self.matches_out(user_id, list(decisions))

    async def matches_out(
        self, user_id: uuid.UUID, decisions: list[MatchDecision]
    ) -> list[MatchOut]:
        out: list[MatchOut] = []
        for decision in decisions:
            observation = await self._observations.get(user_id, decision.observation_id)
            if observation is None:
                continue
            if (
                decision.decision == MatchDecisionStatus.PENDING
                and observation.status != ObservationStatus.PENDING_REVIEW
            ):
                continue  # answered some other way: nothing to ask any more
            transaction = (
                await self._transaction_out(user_id, decision.transaction_id)
                if decision.transaction_id
                else None
            )
            out.append(
                MatchOut(
                    id=decision.id,
                    decision=decision.decision,
                    score=float(decision.score) if decision.score is not None else 0.0,
                    features=decision.features_json or {},
                    observation=_observation_out(observation),
                    transaction=transaction,
                    created_at=decision.created_at,
                )
            )
        return out

    async def preview_bank_row(
        self, user_id: uuid.UUID, observation: Observation
    ) -> BankRowMatchOut | None:
        """For the import review: will this row be merged, or asked about? Writes nothing."""
        if observation.status != ObservationStatus.PENDING_REVIEW:
            return None
        saved = (observation.extraction_json or {}).get("suggestions", {})
        raw_merchant_id = (saved.get("merchant") or {}).get("merchant_id")
        evaluation = await self.evaluate(
            user_id,
            source=observation.source,
            direction=observation.direction,
            amount_minor=observation.amount_minor,
            day=observation.obs_date,
            at=observation.obs_time,
            merchant_id=uuid.UUID(raw_merchant_id) if raw_merchant_id else None,
            merchant_name=observation.merchant_raw or "",
            installment_seq=observation.installment_seq,
            installment_count=observation.installment_count,
        )
        result = evaluation.result
        if result.outcome not in (MatchOutcome.AUTO, MatchOutcome.SUGGEST):
            return None
        best = result.strong[0]
        candidate = evaluation.candidates[best.transaction_id]
        transaction = await self._transaction_out(
            user_id, best.transaction_id, sources=list(candidate.sources)
        )
        if transaction is None:
            return None
        return BankRowMatchOut(
            state="AUTO" if result.outcome == MatchOutcome.AUTO else "SUGGEST",
            score=best.score,
            transaction=transaction,
        )

    async def _transaction_out(
        self,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        *,
        sources: list[ObservationSource] | None = None,
    ) -> MatchTransactionOut | None:
        row = await self._transactions.get_row(user_id, transaction_id)
        if row is None:
            return None
        if sources is None:
            evidence = await self._transactions.evidence(user_id, transaction_id)
            sources = sorted(
                {o.source for o in evidence if o.status == ObservationStatus.CONFIRMED},
                key=lambda s: s.value,
            )
        t = row.transaction
        return MatchTransactionOut(
            id=t.id,
            merchant_display=t.merchant_display,
            category_key=row.category_key,
            purchase_date=t.purchase_date,
            purchase_time=t.purchase_time,
            total_minor=t.total_minor,
            sources=sources,
        )


def _pending_of(observation: Observation) -> dict[str, Any]:
    pending = (observation.extraction_json or {}).get(PENDING_KEY)
    if not isinstance(pending, dict):
        raise MatchNotPendingError()
    return pending


def without_pending(saved: dict[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in (saved or {}).items() if key != PENDING_KEY}


def _observation_out(observation: Observation) -> MatchObservationOut:
    pending = (observation.extraction_json or {}).get(PENDING_KEY)
    if isinstance(pending, dict):
        fields = TxFields.from_json(pending)
        return MatchObservationOut(
            id=observation.id,
            source=observation.source,
            merchant_display=fields.merchant_display,
            purchase_date=fields.purchase_date,
            purchase_time=fields.purchase_time,
            total_minor=fields.total_minor,
        )
    return MatchObservationOut(
        id=observation.id,
        source=observation.source,
        merchant_display=observation.merchant_raw or "",
        purchase_date=observation.obs_date or date.today(),
        purchase_time=observation.obs_time,
        total_minor=observation.amount_minor or 0,
    )


__all__ = ["Evaluation", "MatchService", "Unmerged", "side_of", "without_pending"]
