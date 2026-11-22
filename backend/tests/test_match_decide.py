"""The pure decision of the matching engine: thresholds, ties, the installment hook, precedence."""

import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.matching.engine import (
    MatchOutcome,
    ScoredCandidate,
    Thresholds,
    decide,
    defers_to_installments,
    source_rank,
)
from app.matching.features import MatchFeatures
from app.models.enums import ObservationSource

T = Thresholds(auto=95.0, suggest=70.0, record_min=50.0)


def candidate(score: float, transaction_id: uuid.UUID | None = None) -> ScoredCandidate:
    features = MatchFeatures(
        amount_rel_diff=0.0,
        amount_score=50.0,
        date_diff_days=0,
        date_score=20.0,
        merchant_alias_hit=False,
        merchant_token_set_ratio=None,
        merchant_token_sort_ratio=None,
        merchant_score=None,
        time_diff_minutes=None,
        time_score=None,
        available_max=70.0,
        earned=score * 0.7,
        score=score,
        source_pair="RECEIPT|BANK_SCREENSHOT",
        has_time_new=False,
        has_time_candidate=False,
    )
    return ScoredCandidate(transaction_id or uuid.uuid4(), features)


def test_one_strong_candidate_at_the_auto_threshold_is_merged_automatically() -> None:
    assert decide([candidate(95.0)], T).outcome == MatchOutcome.AUTO


def test_one_candidate_just_below_auto_is_a_suggestion() -> None:
    assert decide([candidate(94.99)], T).outcome == MatchOutcome.SUGGEST


def test_a_candidate_at_the_suggest_threshold_is_a_suggestion() -> None:
    assert decide([candidate(70.0)], T).outcome == MatchOutcome.SUGGEST


def test_a_candidate_below_the_suggest_threshold_means_a_new_purchase() -> None:
    result = decide([candidate(69.99)], T)
    assert result.outcome == MatchOutcome.NEW
    assert result.strong == ()


def test_two_perfect_candidates_are_never_merged_automatically() -> None:
    result = decide([candidate(100.0), candidate(100.0)], T)
    assert result.outcome == MatchOutcome.SUGGEST
    assert len(result.strong) == 2


def test_a_perfect_candidate_next_to_a_weak_one_is_still_automatic() -> None:
    # the 55-point one is recorded but is not "another candidate" for the auto rule
    result = decide([candidate(100.0), candidate(55.0)], T)
    assert result.outcome == MatchOutcome.AUTO
    assert len(result.strong) == 1 and len(result.candidates) == 2


def test_candidates_below_the_record_minimum_are_not_kept() -> None:
    result = decide([candidate(49.99), candidate(50.0)], T)
    assert [c.score for c in result.candidates] == [50.0]


def test_candidates_come_back_best_first() -> None:
    result = decide([candidate(72.0), candidate(88.0), candidate(60.0)], T)
    assert [c.score for c in result.candidates] == [88.0, 72.0, 60.0]


def test_the_answer_does_not_depend_on_the_order_candidates_arrive_in() -> None:
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    first = decide([candidate(80.0, a), candidate(80.0, b)], T)
    second = decide([candidate(80.0, b), candidate(80.0, a)], T)
    assert [c.transaction_id for c in first.candidates] == [a, b]
    assert [c.transaction_id for c in second.candidates] == [a, b]


def test_no_candidates_means_a_new_purchase() -> None:
    assert decide([], T).outcome == MatchOutcome.NEW


def test_other_thresholds_change_the_outcome() -> None:
    lenient = Thresholds(auto=80.0, suggest=60.0, record_min=50.0)
    assert decide([candidate(85.0)], T).outcome == MatchOutcome.SUGGEST
    assert decide([candidate(85.0)], lenient).outcome == MatchOutcome.AUTO


# ---- the hook for P10 -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seq", "count", "defers"),
    [
        (None, None, False),
        (None, 1, False),
        (1, 3, True),  # "(1/3)": one payment of a plan
        (3, 3, True),
        (2, None, True),  # a k without an n is still a marker
        (None, 3, True),  # "3 TAKSİTLİ": the purchase side of a plan
        (None, 12, True),
    ],
)
def test_installment_rows_are_deferred_to_the_installment_matcher(
    seq: int | None, count: int | None, defers: bool
) -> None:
    assert defers_to_installments(seq, count) is defers


# ---- precedence (spec 7.5) --------------------------------------------------------------------


def test_the_source_precedence_is_qr_receipt_bank_manual() -> None:
    order = [
        ObservationSource.EINVOICE_QR,
        ObservationSource.RECEIPT,
        ObservationSource.BANK_SCREENSHOT,
        ObservationSource.MANUAL,
    ]
    ranks = [source_rank(source) for source in order]
    assert ranks == sorted(ranks, reverse=True)
    assert len(set(ranks)) == 4


# ---- the settings -----------------------------------------------------------------------------


def test_the_defaults_are_the_spec_thresholds() -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert (settings.match_auto, settings.match_suggest, settings.match_record_min) == (
        95.0,
        70.0,
        50.0,
    )
    assert Thresholds.from_settings(settings) == T


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Settings(match_auto=60.0, match_suggest=70.0)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(match_suggest=40.0, match_record_min=50.0)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(match_auto=101.0)  # type: ignore[call-arg]
