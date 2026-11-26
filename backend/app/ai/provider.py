"""The AI provider layer (spec 14).

Everything outside `app/ai/providers/` talks to the model only through `AIProvider`. No provider
SDK may be imported outside `app/ai/providers/` (test_no_provider_leak.py checks the imports).

Deviation from the spec text, recorded in DECISIONS: `extract_receipt` returns the model's raw
output (`RawReceiptExtraction`, plain strings); `app/ai/validation.py` turns it into the spec 5.2
`ReceiptExtraction`. That keeps all number parsing and checking deterministic and in one place.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.ai.assistant import AssistantExecutor, AssistantResult, ChatMessage, ToolSpec
from app.ai.schemas import RawBankRow, RawReceiptExtraction
from app.core.config import Settings
from app.models.enums import CategoryKey

call_logger = logging.getLogger("receiptbox.ai")


class ProviderError(Exception):
    """The provider could not deliver an extraction. Messages never contain receipt text."""


class ProviderConfigError(ProviderError):
    """Missing key or model name, or an unknown AI_PROVIDER."""


class ProviderUnavailableError(ProviderError):
    """Timeout, network failure, quota (429) or server error that outlasted the retries."""


class ProviderOutputError(ProviderError):
    """The model answered, but not with a valid ReceiptExtraction, also after the retry."""


@dataclass(frozen=True)
class ExtractionHints:
    """Context that is safe to give the model. (The capture date is deliberately not used to
    fill in a missing receipt date: dates are never guessed.)"""

    capture_date: date
    source: str


@dataclass(frozen=True)
class CallMeta:
    """What is known about one provider call. Never contains text."""

    provider: str
    model: str
    prompt_version: str


class AIProvider(Protocol):
    name: str
    model: str
    prompt_version: str

    def extract_receipt(self, masked_text: str, hints: ExtractionHints) -> RawReceiptExtraction: ...

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[RawBankRow]: ...

    def classify_category(self, merchant: str, items: list[str]) -> CategoryKey: ...

    def write_commentary(self, facts: str) -> str:
        """P11: one or two sentences about a spending comparison. `facts` contains only numbers
        the app computed (totals, change, category amounts): never transactions or shops."""
        ...

    def run_assistant(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        executor: AssistantExecutor,
    ) -> AssistantResult:
        """P14: the model's function-calling loop (see app/ai/assistant.py). Blocking: called in
        a worker thread. Raises ProviderUnavailableError on timeout / quota / network failure."""
        ...


def log_call(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    latency_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
    outcome: str,
) -> None:
    """One log line per provider call: provider, model, prompt version, latency, token counts.
    Never the content (the JSON formatter only emits whitelisted fields)."""
    call_logger.info(
        "ai_call",
        extra={
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "outcome": outcome,
        },
    )


def get_provider(settings: Settings) -> AIProvider:
    """Build the provider named by AI_PROVIDER. Imports are local so that the SDK is only
    loaded when it is used."""
    name = settings.ai_provider.strip().lower()
    if name == "fake":
        from app.ai.providers.fake import FakeProvider

        return FakeProvider.from_directory(settings.ai_fake_fixtures_dir)
    if name == "gemini":
        from app.ai.providers.gemini import GeminiProvider

        api_key = settings.gemini_api_key.get_secret_value()
        if not api_key:
            raise ProviderConfigError("GEMINI_API_KEY is not set.")
        return GeminiProvider(
            api_key=api_key,
            model=settings.ai_model_extract,
            assistant_model=settings.ai_model_assistant,
            timeout_seconds=settings.ai_timeout_seconds,
            thinking_level=settings.ai_thinking_level.strip() or None,
        )
    raise ProviderConfigError("AI_PROVIDER must be 'gemini' or 'fake'.")
