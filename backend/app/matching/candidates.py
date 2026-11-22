"""Candidate generation (spec 7.1 step 3, P09): which existing purchases could this be?

Every condition is in the query, and the user's id is the first one. A candidate is a transaction

* of the same user, not deleted, of kind PURCHASE;
* at most 3 days away from the new observation;
* within 2 % of its amount (relative to the larger of the two, as the score is);
* with NO confirmed observation of the same source (a purchase has at most one receipt, one bank
  row ... spec 6.3: this is why two identical coffees from the bank stay two transactions).
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.features import AMOUNT_ZERO_AT, MAX_CANDIDATE_DAYS
from app.models import Observation, Transaction
from app.models.enums import ObservationSource, ObservationStatus, TransactionKind


@dataclass(frozen=True)
class Candidate:
    transaction: Transaction
    sources: tuple[ObservationSource, ...]  # the sources already attached to it


async def find_candidates(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: ObservationSource,
    amount_minor: int,
    day: date,
    exclude_transaction_id: uuid.UUID | None = None,
) -> list[Candidate]:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    larger = func.greatest(Transaction.total_minor, amount_minor)
    same_source_evidence = exists().where(
        and_(
            Observation.transaction_id == Transaction.id,
            Observation.user_id == user_id,
            Observation.status == ObservationStatus.CONFIRMED,
            Observation.source == source,
        )
    )
    statement = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
        Transaction.kind == TransactionKind.PURCHASE,
        Transaction.purchase_date >= day - timedelta(days=MAX_CANDIDATE_DAYS),
        Transaction.purchase_date <= day + timedelta(days=MAX_CANDIDATE_DAYS),
        func.abs(Transaction.total_minor - amount_minor) <= AMOUNT_ZERO_AT * larger,
        ~same_source_evidence,
    )
    if exclude_transaction_id is not None:
        statement = statement.where(Transaction.id != exclude_transaction_id)
    transactions = list((await session.execute(statement)).scalars().all())
    if not transactions:
        return []

    evidence = await session.execute(
        select(Observation.transaction_id, Observation.source).where(
            Observation.user_id == user_id,
            Observation.status == ObservationStatus.CONFIRMED,
            Observation.transaction_id.in_([t.id for t in transactions]),
        )
    )
    sources: dict[uuid.UUID, list[ObservationSource]] = {}
    for transaction_id, observation_source in evidence.all():
        sources.setdefault(transaction_id, []).append(observation_source)
    return [
        Candidate(t, tuple(sorted(sources.get(t.id, []), key=lambda s: s.value)))
        for t in transactions
    ]
