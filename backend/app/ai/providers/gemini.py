"""GeminiProvider: receipt extraction and category classification with the `google-genai` SDK
(the only place that imports it).

* Constrained output: the response must match `RawReceiptExtraction` (JSON schema), or be one
  of the 13 category keys (enum).
* 1 retry when the answer is not valid for the schema.
* Exponential back-off (1 s, 2 s, 4 s) on 429 and 5xx, within one overall time budget of
  `timeout_seconds` (30 s by default).
* The model name comes from settings (AI_MODEL_EXTRACT); nothing is hard-coded here.
* Logs provider, model, prompt version, latency and token counts. Never the content, and error
  messages of the SDK are not logged or passed on (they could echo parts of the request).
"""

import time
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ai.prompts import CATEGORY_CLASSIFY, RECEIPT_EXTRACT, load_prompt
from app.ai.provider import (
    ExtractionHints,
    ProviderOutputError,
    ProviderUnavailableError,
    log_call,
)
from app.ai.schemas import RawReceiptExtraction
from app.models.enums import CategoryKey

BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
_NO_ANSWER_IN_TIME = "The AI provider did not answer in time."


class GeminiProvider:
    name = "gemini"
    prompt_version = RECEIPT_EXTRACT

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        thinking_level: str | None = None,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        self._timeout_seconds = timeout_seconds
        self._thinking = (
            types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None
        )
        self._client = client if client is not None else genai.Client(api_key=api_key)
        self._sleep = sleep
        self._clock = clock
        self._receipt_prompt = load_prompt(RECEIPT_EXTRACT)
        self._category_prompt = load_prompt(CATEGORY_CLASSIFY)

    def extract_receipt(self, masked_text: str, hints: ExtractionHints) -> RawReceiptExtraction:
        return self._generate(
            masked_text,
            system_prompt=self._receipt_prompt,
            prompt_version=RECEIPT_EXTRACT,
            mime_type="application/json",
            schema=RawReceiptExtraction,
            parse=lambda text: RawReceiptExtraction.model_validate_json(text),
        )

    def classify_category(self, merchant: str, items: list[str]) -> CategoryKey:
        lines = [f"Merchant: {merchant.strip() or '(unknown)'}"]
        if items:
            lines.append("Items: " + "; ".join(item.strip() for item in items[:20] if item.strip()))
        return self._generate(
            "\n".join(lines),
            system_prompt=self._category_prompt,
            prompt_version=CATEGORY_CLASSIFY,
            mime_type="text/x.enum",
            schema=CategoryKey,
            parse=lambda text: CategoryKey(text.strip().strip('"')),
        )

    def _generate(
        self,
        contents: str,
        *,
        system_prompt: str,
        prompt_version: str,
        mime_type: str,
        schema: Any,
        parse: Callable[[str], Any],
    ) -> Any:
        started = self._clock()
        deadline = started + self._timeout_seconds
        schema_failures = 0
        backoff_index = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        outcome = "error"
        try:
            while True:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    outcome = "timeout"
                    raise ProviderUnavailableError(_NO_ANSWER_IN_TIME)
                try:
                    response = self._client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type=mime_type,
                            response_schema=schema,
                            temperature=0.0,
                            thinking_config=self._thinking,
                            http_options=types.HttpOptions(timeout=max(1, int(remaining * 1000))),
                        ),
                    )
                except errors.APIError as error:
                    code = getattr(error, "code", None)
                    if code in _RETRYABLE_HTTP_CODES and backoff_index < len(BACKOFF_SECONDS):
                        delay = BACKOFF_SECONDS[backoff_index]
                        backoff_index += 1
                        if self._clock() + delay >= deadline:
                            outcome = "timeout"
                            raise ProviderUnavailableError(_NO_ANSWER_IN_TIME) from None
                        self._sleep(delay)
                        continue
                    outcome = f"http_{code}" if code else "api_error"
                    raise ProviderUnavailableError("The AI provider refused the request.") from None
                except Exception:  # noqa: BLE001  (timeouts and connection errors differ per SDK)
                    outcome = "network_error"
                    raise ProviderUnavailableError(
                        "The AI provider could not be reached."
                    ) from None

                usage = getattr(response, "usage_metadata", None)
                input_tokens = getattr(usage, "prompt_token_count", None)
                output_tokens = getattr(usage, "candidates_token_count", None)
                try:
                    parsed = parse(response.text or "")
                except (ValidationError, ValueError):
                    schema_failures += 1
                    if schema_failures > 1:  # one retry only
                        outcome = "invalid_output"
                        raise ProviderOutputError(
                            "The AI provider's answer did not match the schema."
                        ) from None
                    continue
                outcome = "ok"
                return parsed
        finally:
            log_call(
                provider=self.name,
                model=self.model,
                prompt_version=prompt_version,
                latency_ms=int((self._clock() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                outcome=outcome,
            )

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[Any]:
        raise NotImplementedError("Bank screenshots arrive in P08.")

    def run_assistant(self, messages: list[Any], tools: list[Any], executor: Any) -> Any:
        raise NotImplementedError("The assistant arrives in P14.")
