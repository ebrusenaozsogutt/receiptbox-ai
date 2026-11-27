"""FakeProvider: deterministic fixtures instead of a model. Used by every test and by
`AI_PROVIDER=fake` (offline demos, Swagger). It never touches the network.

Fixtures live in a directory as pairs:
    NN_name.txt        the masked receipt text (the input)
    NN_name.llm.json   what the "model" returns for it (a RawReceiptExtraction)
The answer is looked up by a hash of the input text, so the same text always gives the same
answer and a text without a fixture is an error (a test never silently gets an invented answer).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.ai.assistant import (
    MAX_CORRECTIONS,
    AssistantExecutor,
    AssistantResult,
    ChatMessage,
    ToolSpec,
)
from app.ai.prompts import (
    ASSISTANT,
    BANK_ROWS,
    CATEGORY_CLASSIFY,
    COMPARISON_COMMENTARY,
    RECEIPT_EXTRACT,
)
from app.ai.provider import (
    ExtractionHints,
    ProviderConfigError,
    ProviderOutputError,
    ProviderUnavailableError,
    log_call,
)
from app.ai.schemas import RawBankExtraction, RawBankRow, RawReceiptExtraction
from app.ai.usage import DailyLimitReached
from app.core.text import normalize_alias_key
from app.models.enums import CategoryKey

BACKEND_DIR = Path(__file__).resolve().parents[3]


def text_key(masked_text: str) -> str:
    """Hash used to find the fixture. Line endings and surrounding blank space do not matter."""
    normalized = masked_text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _merchant_key(merchant: str) -> str:
    return normalize_alias_key(merchant)


class FakeProvider:
    name = "fake"
    model = "fake-fixtures"
    assistant_model = "fake-assistant"
    prompt_version = RECEIPT_EXTRACT

    def __init__(
        self,
        answers: dict[str, RawReceiptExtraction] | None = None,
        categories: dict[str, CategoryKey] | None = None,
        bank_answers: dict[str, RawBankExtraction] | None = None,
    ) -> None:
        self._answers = dict(answers or {})
        self._bank_answers = dict(bank_answers or {})
        self.bank_calls = 0  # bank screenshot extractions
        self.bank_hints: list[str | None] = []  # the bank_key of each bank call
        self._categories = {_merchant_key(m): k for m, k in (categories or {}).items()}
        self.calls = 0  # receipt extractions; tests look at this
        self.classify_calls = 0  # category classifications
        # P11: every facts text the comparison commentary received (tests inspect them), the
        # answer it gives, and an error to raise instead.
        self.commentary_inputs: list[str] = []
        self.commentary_answer = "Bu dönemde harcaman önceki döneme göre arttı."
        self.commentary_error: Exception | None = None
        # P14: one script per chat turn (consumed in order), what each turn was asked, the
        # wrapped tool outputs the "model" received and the correction messages it got.
        self.assistant_scripts: list[list[dict[str, Any]]] = []
        self.assistant_requests: list[tuple[list[ChatMessage], list[ToolSpec]]] = []
        self.assistant_tool_outputs: list[list[dict[str, Any]]] = []
        self.assistant_corrections: list[str] = []

    @classmethod
    def from_directory(cls, directory: str | Path) -> "FakeProvider":
        path = Path(directory)
        if not path.is_absolute() and not path.exists():
            path = BACKEND_DIR / path
        if not path.is_dir():
            raise ProviderConfigError("The fake provider's fixtures directory does not exist.")
        answers: dict[str, RawReceiptExtraction] = {}
        bank_answers: dict[str, RawBankExtraction] = {}
        for text_file in sorted(path.glob("*.txt")):
            answer_file = text_file.with_suffix(".llm.json")
            if not answer_file.exists():
                continue
            data = json.loads(answer_file.read_text(encoding="utf-8"))
            text = text_file.read_text(encoding="utf-8")
            if "rows" in data:  # a bank screenshot fixture
                bank_answers[text_key(text)] = RawBankExtraction.model_validate(data)
            else:
                answers[text_key(text)] = RawReceiptExtraction.model_validate(data)
        categories: dict[str, CategoryKey] = {}
        category_file = path / "categories.json"
        if category_file.exists():
            raw = json.loads(category_file.read_text(encoding="utf-8"))
            categories = {merchant: CategoryKey(key) for merchant, key in raw.items()}
        return cls(answers, categories, bank_answers)

    def add(self, masked_text: str, answer: RawReceiptExtraction) -> None:
        self._answers[text_key(masked_text)] = answer

    def extract_receipt(self, masked_text: str, hints: ExtractionHints) -> RawReceiptExtraction:
        self.calls += 1
        answer = self._answers.get(text_key(masked_text))
        log_call(
            provider=self.name,
            model=self.model,
            prompt_version=self.prompt_version,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            outcome="ok" if answer is not None else "no_fixture",
        )
        if answer is None:
            raise ProviderOutputError("The fake provider has no fixture for this text.")
        return answer.model_copy(deep=True)

    def add_bank(self, masked_text: str, answer: RawBankExtraction) -> None:
        self._bank_answers[text_key(masked_text)] = answer

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[RawBankRow]:
        self.bank_calls += 1
        self.bank_hints.append(bank_key)
        answer = self._bank_answers.get(text_key(masked_text))
        log_call(
            provider=self.name,
            model=self.model,
            prompt_version=BANK_ROWS,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            outcome="ok" if answer is not None else "no_fixture",
        )
        if answer is None:
            raise ProviderOutputError("The fake provider has no fixture for this text.")
        return [row.model_copy(deep=True) for row in answer.rows]

    def add_category(self, merchant: str, key: CategoryKey) -> None:
        self._categories[_merchant_key(merchant)] = key

    def classify_category(self, merchant: str, items: list[str]) -> CategoryKey:
        """The key configured for this merchant name. An unknown merchant is an error, like a
        model that gave no usable answer (the caller then falls back to OTHER)."""
        self.classify_calls += 1
        key = self._categories.get(_merchant_key(merchant))
        log_call(
            provider=self.name,
            model=self.model,
            prompt_version=CATEGORY_CLASSIFY,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            outcome="ok" if key is not None else "no_fixture",
        )
        if key is None:
            raise ProviderOutputError("The fake provider has no category for this merchant.")
        return key

    def write_commentary(self, facts: str) -> str:
        self.commentary_inputs.append(facts)
        log_call(
            provider=self.name,
            model=self.model,
            prompt_version=COMPARISON_COMMENTARY,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            outcome="error" if self.commentary_error else "ok",
        )
        if self.commentary_error is not None:
            raise self.commentary_error
        return self.commentary_answer

    # ---- P14: the assistant --------------------------------------------------------------------

    def script_assistant(self, *steps: dict[str, Any]) -> None:
        """Queue the "model's" moves for the next chat turn. A step is one of:
        {"tool": name, "args": {...}}   call a tool; a string argument "$i.path.to.field" is
                                        taken from the output of this turn's i-th tool call
        {"answer": text}                answer; if the number check sends a correction, the
                                        script continues with its next answer step
        {"error": "unavailable"}        fail like a timeout / 429
        `args` and `answer` may also be callables that get this turn's tool outputs."""
        self.assistant_scripts.append(list(steps))

    def run_assistant(
        self, messages: list[ChatMessage], tools: list[ToolSpec], executor: AssistantExecutor
    ) -> AssistantResult:
        self.assistant_requests.append((list(messages), list(tools)))
        outputs: list[dict[str, Any]] = []
        self.assistant_tool_outputs.append(outputs)
        log_call(
            provider=self.name,
            model=self.assistant_model,
            prompt_version=ASSISTANT,
            latency_ms=0,
            input_tokens=None,
            output_tokens=None,
            outcome="ok" if self.assistant_scripts else "no_fixture",
        )
        if not self.assistant_scripts:
            raise ProviderOutputError("The fake provider has no assistant script.")
        corrections = 0
        last_answer: str | None = None
        for step in self.assistant_scripts.pop(0):
            if "error" in step:
                if step["error"] == "daily_limit":
                    raise DailyLimitReached("The daily limit of free AI requests is used up.")
                raise ProviderUnavailableError("The AI provider refused the request.")
            if "tool" in step:
                args = step.get("args") or {}
                args = args(outputs) if callable(args) else _resolve(args, outputs)
                outputs.append(executor.call_tool(step["tool"], args))
                continue
            answer = step["answer"]
            last_answer = answer(outputs) if callable(answer) else answer
            correction = executor.check_answer(last_answer)
            if correction is None or corrections >= MAX_CORRECTIONS:
                return AssistantResult(answer=last_answer, corrections=corrections)
            corrections += 1
            self.assistant_corrections.append(correction)
        if last_answer is not None:
            return AssistantResult(answer=last_answer, corrections=corrections)
        raise ProviderOutputError("The fake assistant script has no answer.")


def _resolve(value: Any, outputs: list[dict[str, Any]]) -> Any:
    """ "$0.products.0.product_id" -> outputs[0]["data"]["products"][0]["product_id"]."""
    if isinstance(value, dict):
        return {key: _resolve(item, outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, outputs) for item in value]
    if isinstance(value, str) and value.startswith("$") and value[1:2].isdigit():
        index, *path = value[1:].split(".")
        node: Any = outputs[int(index)].get("data", {})
        for part in path:
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node
    return value
