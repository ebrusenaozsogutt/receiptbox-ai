"""The decision of the matching engine (spec 7.1, 7.4, 7.5, P09). Pure: scores in, outcome out.

`decide` turns the scored candidates of one new observation into one of

* `AUTO`        exactly one candidate reaches the suggest threshold and it reaches the auto
                threshold: the observation is merged into that transaction (with an Undo);
* `SUGGEST`     at least one candidate reaches the suggest threshold but the auto rule does not
                hold (score between the thresholds, or more than one candidate): the user decides
                and NO new transaction exists meanwhile;
* `NEW`         no candidate reaches the suggest threshold: a new transaction.

`INSTALLMENT` is not decided here: an observation with a k/n marker (or a total with "n taksit")
is not a 1:1 purchase and `defers_to_installments` sends it to the installment matcher of P10.

The thresholds come from the settings (`MATCH_AUTO`, `MATCH_SUGGEST`, `MATCH_RECORD_MIN`).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings
from app.matching.features import MatchFeatures
from app.models.enums import ObservationSource

# Spec 7.5: which source wins when two observations of one purchase disagree.
SOURCE_PRECEDENCE: dict[ObservationSource, int] = {
    ObservationSource.EINVOICE_QR: 4,
    ObservationSource.RECEIPT: 3,
    ObservationSource.BANK_SCREENSHOT: 2,
    ObservationSource.MANUAL: 1,
}


class MatchOutcome(StrEnum):
    NEW = "NEW"
    AUTO = "AUTO"
    SUGGEST = "SUGGEST"
    INSTALLMENT = "INSTALLMENT"  # not decided here: P10 takes over


@dataclass(frozen=True)
class Thresholds:
    auto: float
    suggest: float
    record_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(
            auto=settings.match_auto,
            suggest=settings.match_suggest,
            record_min=settings.match_record_min,
        )


@dataclass(frozen=True)
class ScoredCandidate:
    transaction_id: uuid.UUID
    features: MatchFeatures

    @property
    def score(self) -> float:
        return self.features.score


@dataclass(frozen=True)
class MatchResult:
    outcome: MatchOutcome
    # Every candidate at or above `record_min`, best first. All of them are stored.
    candidates: tuple[ScoredCandidate, ...] = ()
    # The ones at or above `suggest`: what the user is asked about (AUTO: exactly one).
    strong: tuple[ScoredCandidate, ...] = ()


def defers_to_installments(installment_seq: int | None, installment_count: int | None) -> bool:
    """The hook for P10. A row with a k/n marker is one payment of a plan, and a receipt or slip
    with more than one installment is the purchase side of a plan: neither is merged 1:1 here."""
    return installment_seq is not None or (installment_count or 0) > 1


def source_rank(source: ObservationSource) -> int:
    return SOURCE_PRECEDENCE[source]


def decide(scored: list[ScoredCandidate], thresholds: Thresholds) -> MatchResult:
    """Best first; ties by transaction id, so the answer never depends on the arrival order."""
    ordered = sorted(
        (candidate for candidate in scored if candidate.score >= thresholds.record_min),
        key=lambda candidate: (-candidate.score, str(candidate.transaction_id)),
    )
    strong = tuple(candidate for candidate in ordered if candidate.score >= thresholds.suggest)
    if not strong:
        return MatchResult(MatchOutcome.NEW, tuple(ordered), ())
    if len(strong) == 1 and strong[0].score >= thresholds.auto:
        return MatchResult(MatchOutcome.AUTO, tuple(ordered), strong)
    return MatchResult(MatchOutcome.SUGGEST, tuple(ordered), strong)
