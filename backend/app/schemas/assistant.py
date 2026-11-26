"""P14 assistant API (spec 13.1, 16)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_QUESTION_CHARS = 500
MAX_HISTORY_ANSWER_CHARS = 2000


class HistoryTurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    answer: str = Field(min_length=1, max_length=MAX_HISTORY_ANSWER_CHARS)


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[HistoryTurnIn] = Field(
        default_factory=list,
        max_length=6,
        description="The last turns shown on the phone (question and answer text only), oldest "
        "first. At most 6.",
    )


class ActionOut(BaseModel):
    type: Literal["OPEN_TRANSACTIONS", "OPEN_PRODUCT", "OPEN_DOCUMENT", "OPEN_INSTALLMENTS"]
    label: str = Field(description="Turkish button text.")
    params: dict[str, str] = Field(
        description="OPEN_TRANSACTIONS: from, to (YYYY-MM-DD), category, q. OPEN_PRODUCT: id. "
        "OPEN_DOCUMENT: id, pdf ('true'/'false'). OPEN_INSTALLMENTS: month (YYYY-MM)."
    )


class ToolCallOut(BaseModel):
    name: str
    args: dict[str, Any]


class ChatOut(BaseModel):
    answer: str
    actions: list[ActionOut]
    tool_calls: list[ToolCallOut] = Field(
        description="The tools the assistant used, with their arguments (never their output)."
    )
