"""Request and response shapes of the matching endpoints (spec 7, 16, P09). Money is `*_minor`."""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import CategoryKey, MatchDecisionStatus, ObservationSource


class MatchTransactionOut(BaseModel):
    """An existing purchase a new observation may be the same as."""

    id: uuid.UUID
    merchant_display: str
    category_key: CategoryKey | None
    purchase_date: dt.date
    purchase_time: dt.time | None
    total_minor: int
    sources: list[ObservationSource] = Field(description="What is already attached to it.")


class MatchObservationOut(BaseModel):
    """The new observation waiting for the user's answer, as the user reviewed it."""

    id: uuid.UUID
    source: ObservationSource
    merchant_display: str
    purchase_date: dt.date
    purchase_time: dt.time | None
    total_minor: int


class MatchOut(BaseModel):
    """One suggestion: "this new thing may be the same as that purchase"."""

    id: uuid.UUID = Field(description="The decision id: accept or reject with it.")
    decision: MatchDecisionStatus
    score: float = Field(description="0-100, spec 7.3")
    features: dict[str, Any]
    observation: MatchObservationOut
    transaction: MatchTransactionOut | None
    created_at: dt.datetime


class BankRowMatchOut(BaseModel):
    """Shown on a bank row of the import review: it WILL be merged (AUTO), or the user will be
    asked after saving (SUGGEST). Nothing is stored for a preview."""

    state: Literal["AUTO", "SUGGEST"]
    score: float
    transaction: MatchTransactionOut


class MergeOut(BaseModel):
    """What happened when an observation was attached to an existing purchase."""

    decision_id: uuid.UUID
    decision: MatchDecisionStatus
    score: float | None
    observation_id: uuid.UUID


class SuggestionResponse(BaseModel):
    """The answer of a save that needs the user's decision first: no transaction exists yet."""

    outcome: Literal["SUGGESTED"] = "SUGGESTED"
    matches: list[MatchOut]


class UnmergeRequest(BaseModel):
    observation_id: uuid.UUID
