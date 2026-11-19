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

from app.ai.prompts import RECEIPT_EXTRACT
from app.ai.provider import (
    ExtractionHints,
    ProviderConfigError,
    ProviderOutputError,
    log_call,
)
from app.ai.schemas import RawReceiptExtraction
from app.models.enums import CategoryKey

BACKEND_DIR = Path(__file__).resolve().parents[3]


def text_key(masked_text: str) -> str:
    """Hash used to find the fixture. Line endings and surrounding blank space do not matter."""
    normalized = masked_text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class FakeProvider:
    name = "fake"
    model = "fake-fixtures"
    prompt_version = RECEIPT_EXTRACT

    def __init__(self, answers: dict[str, RawReceiptExtraction] | None = None) -> None:
        self._answers = dict(answers or {})
        self.calls = 0  # tests look at this

    @classmethod
    def from_directory(cls, directory: str | Path) -> "FakeProvider":
        path = Path(directory)
        if not path.is_absolute() and not path.exists():
            path = BACKEND_DIR / path
        if not path.is_dir():
            raise ProviderConfigError("The fake provider's fixtures directory does not exist.")
        answers: dict[str, RawReceiptExtraction] = {}
        for text_file in sorted(path.glob("*.txt")):
            answer_file = text_file.with_suffix(".llm.json")
            if not answer_file.exists():
                continue
            answer = RawReceiptExtraction.model_validate(
                json.loads(answer_file.read_text(encoding="utf-8"))
            )
            answers[text_key(text_file.read_text(encoding="utf-8"))] = answer
        return cls(answers)

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

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[Any]:
        raise NotImplementedError("Bank screenshots arrive in P08.")

    def classify_category(self, merchant: str, items: list[str]) -> CategoryKey:
        raise NotImplementedError("Categorisation arrives in P06.")

    def run_assistant(self, messages: list[Any], tools: list[Any], executor: Any) -> Any:
        raise NotImplementedError("The assistant arrives in P14.")
