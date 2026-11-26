"""Provider-neutral types of the assistant loop (spec 13, 14; P14).

`AIProvider.run_assistant(messages, tools, executor)` runs the model's function-calling loop in a
worker thread. Everything that touches user data or decides what is allowed lives in the
executor, which the service supplies:

- `call_tool(name, args)` runs one of the 8 tools for the signed-in user (the `user_id` is the
  executor's, never an argument) and returns the output wrapped as data;
- `check_answer(answer)` returns a correction message when the answer uses a number that no tool
  output contains, else None;
- `tools_left()` / `deadline`: at most MAX_TOOL_CALLS calls and TURN_BUDGET_SECONDS per turn.

A provider sends at most MAX_CORRECTIONS correction(s) back to the model; the service checks the
final answer again and falls back to a templated answer.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

MAX_TOOL_CALLS = 4
TURN_BUDGET_SECONDS = 20.0
MAX_CORRECTIONS = 1


@dataclass(frozen=True)
class ToolSpec:
    """What the model is told about a tool: its name, what it does and its JSON schema."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    """`system` (the prompt), `user` (a question) or `assistant` (an earlier answer)."""

    role: Literal["system", "user", "assistant"]
    text: str


@dataclass
class AssistantResult:
    answer: str
    corrections: int = 0
    # Provider details for the turn log (never text).
    input_tokens: int | None = None
    output_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class AssistantExecutor(Protocol):
    deadline: float  # time.monotonic() value by which the turn must be over

    def tools_left(self) -> int: ...

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...

    def check_answer(self, answer: str) -> str | None: ...
