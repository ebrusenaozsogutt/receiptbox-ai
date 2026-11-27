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

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

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
    load_bank_prompt,
    load_prompt,
)
from app.ai.provider import (
    ExtractionHints,
    ProviderOutputError,
    ProviderUnavailableError,
    log_call,
)
from app.ai.schemas import RawBankExtraction, RawBankRow, RawCommentary, RawReceiptExtraction
from app.ai.usage import DailyLimitReached, RequestGate, ResponseCache
from app.models.enums import CategoryKey

BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def _cache_key(model: str, contents: Any, config: types.GenerateContentConfig) -> str:
    """Everything that decides the answer, without the per-call timeout."""

    def plain(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(exclude_none=True)
        if isinstance(value, list):
            return [plain(item) for item in value]
        return value

    material = {
        "model": model,
        "contents": plain(contents),
        "config": config.model_dump(exclude={"http_options"}, exclude_none=True),
    }
    text = json.dumps(material, default=str, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        assistant_model: str | None = None,
        gate: RequestGate | None = None,
        response_cache: ResponseCache | None = None,
        pace_seconds: float = 0.0,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        # P14: the assistant may use another model (AI_MODEL_ASSISTANT); default: the same one.
        self.assistant_model = assistant_model or model
        self._timeout_seconds = timeout_seconds
        self._thinking = (
            types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None
        )
        self._client = client if client is not None else genai.Client(api_key=api_key)
        self._sleep = sleep
        self._clock = clock
        # D-016: every real request passes the daily cap; a cache hit (P15 experiments) is free.
        self._gate = gate
        self._cache = response_cache
        # P15 experiments: at least this long between two real requests (free-tier per-minute
        # limits). The app does not pace (0).
        self._pace_seconds = pace_seconds
        self._last_request: float | None = None
        self._receipt_prompt = load_prompt(RECEIPT_EXTRACT)
        self._category_prompt = load_prompt(CATEGORY_CLASSIFY)
        self._commentary_prompt = load_prompt(COMPARISON_COMMENTARY)

    def extract_receipt(self, masked_text: str, hints: ExtractionHints) -> RawReceiptExtraction:
        return self._generate(
            masked_text,
            system_prompt=self._receipt_prompt,
            prompt_version=RECEIPT_EXTRACT,
            mime_type="application/json",
            schema=RawReceiptExtraction,
            parse=lambda text: RawReceiptExtraction.model_validate_json(text),
        )

    def extract_receipt_image(self, image: bytes, mime_type: str) -> RawReceiptExtraction:
        """P15 E1 system S5 ONLY (the privacy-unfriendly baseline of spec 19): the photo itself,
        unmasked, goes to the model. The app never calls this; the experiment calls it only for
        receipts the owner allowed (gold.json "s5_allowed")."""
        return self._generate(
            [
                types.Part.from_bytes(data=image, mime_type=mime_type),
                "Bu fişin fotoğrafını oku.",
            ],
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

    def write_commentary(self, facts: str) -> str:
        answer: RawCommentary = self._generate(
            facts,
            system_prompt=self._commentary_prompt,
            prompt_version=COMPARISON_COMMENTARY,
            mime_type="application/json",
            schema=RawCommentary,
            parse=lambda text: RawCommentary.model_validate_json(text),
        )
        return answer.text

    def _call(self, *, model: str, contents: Any, config: types.GenerateContentConfig) -> Any:
        """One generate_content call. A cached answer (P15 experiments) costs no request; a real
        request first passes the daily cap (D-016) and may raise DailyLimitReached."""
        key = _cache_key(model, contents, config) if self._cache is not None else None
        if key is not None and self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return types.GenerateContentResponse.model_validate_json(cached)
        if self._gate is not None:
            self._gate.take(model)
        if self._pace_seconds and self._last_request is not None:
            wait = self._last_request + self._pace_seconds - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()
        response = self._client.models.generate_content(
            model=model, contents=contents, config=config
        )
        if key is not None and self._cache is not None:
            self._cache.put(key, response.model_dump_json(exclude_none=True))
        return response

    def _generate(
        self,
        contents: Any,
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
                    response = self._call(
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
                except DailyLimitReached:
                    outcome = "daily_limit"
                    raise
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

    def extract_bank_rows(self, masked_text: str, bank_key: str | None) -> list[RawBankRow]:
        """The rows on a bank screenshot. A supported bank's hints (`prompts/banks/<bank>.md`) are
        added to the system prompt; any other bank is read with the general prompt only."""
        extraction: RawBankExtraction = self._generate(
            masked_text,
            system_prompt=load_bank_prompt(bank_key),
            prompt_version=BANK_ROWS,
            mime_type="application/json",
            schema=RawBankExtraction,
            parse=lambda text: RawBankExtraction.model_validate_json(text),
        )
        return extraction.rows

    # ---- P14: the assistant ----------------------------------------------------------------

    def run_assistant(
        self, messages: list[ChatMessage], tools: list[ToolSpec], executor: AssistantExecutor
    ) -> AssistantResult:
        """Manual function calling (the SDK's automatic calling is off): the model asks for tool
        calls, the executor runs them for the signed-in user, their wrapped outputs go back;
        until the model answers in text. After MAX_TOOL_CALLS the model may only answer. An
        answer that fails the number check gets one correction message. The whole turn must end
        by `executor.deadline`; 429 / 5xx are retried with back-off inside it."""
        system = "\n\n".join(m.text for m in messages if m.role == "system")
        contents: list[types.Content] = [
            types.Content(
                role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.text)]
            )
            for m in messages
            if m.role != "system"
        ]
        declarations = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters_json_schema=t.parameters
            )
            for t in tools
        ]
        started = self._clock()
        state: dict[str, Any] = {"outcome": "error", "backoff": 0}
        input_tokens = output_tokens = 0
        corrections = 0
        try:
            while True:
                config = self._assistant_config(
                    system, declarations, "AUTO" if executor.tools_left() > 0 else "NONE"
                )
                response = self._send(
                    contents=contents, config=config, deadline=executor.deadline, state=state
                )
                usage = getattr(response, "usage_metadata", None)
                input_tokens += getattr(usage, "prompt_token_count", None) or 0
                output_tokens += getattr(usage, "candidates_token_count", None) or 0
                candidates = getattr(response, "candidates", None) or []
                model_turn = candidates[0].content if candidates else None
                calls = getattr(response, "function_calls", None) or []
                if calls:
                    if model_turn is not None:
                        contents.append(model_turn)  # keeps the model's thought signatures
                    parts = [
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call.id,
                                name=call.name,
                                response=executor.call_tool(call.name or "", dict(call.args or {})),
                            )
                        )
                        for call in calls
                    ]
                    contents.append(types.Content(role="user", parts=parts))
                    continue
                text = (response.text or "").strip()
                correction = executor.check_answer(text) if text else None
                if correction is not None and corrections < MAX_CORRECTIONS:
                    corrections += 1
                    if model_turn is not None:
                        contents.append(model_turn)
                    contents.append(types.Content(role="user", parts=[types.Part(text=correction)]))
                    continue
                state["outcome"] = "ok" if correction is None else "unchecked_answer"
                return AssistantResult(
                    answer=text,
                    corrections=corrections,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
        finally:
            log_call(
                provider=self.name,
                model=self.assistant_model,
                prompt_version=ASSISTANT,
                latency_ms=int((self._clock() - started) * 1000),
                input_tokens=input_tokens or None,
                output_tokens=output_tokens or None,
                outcome=state["outcome"],
            )

    def _assistant_config(
        self, system: str, declarations: list[types.FunctionDeclaration], mode: str
    ) -> Callable[[float], types.GenerateContentConfig]:
        def make(remaining: float) -> types.GenerateContentConfig:
            return types.GenerateContentConfig(
                system_instruction=system,
                tools=[types.Tool(function_declarations=declarations)],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode=mode)
                ),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.0,
                thinking_config=self._thinking,
                http_options=types.HttpOptions(timeout=max(1, int(remaining * 1000))),
            )

        return make

    def _send(
        self,
        *,
        contents: list[types.Content],
        config: Callable[[float], types.GenerateContentConfig],
        deadline: float,
        state: dict[str, Any],
    ) -> Any:
        """One request of the assistant loop, with back-off on 429 / 5xx before `deadline`."""
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                state["outcome"] = "timeout"
                raise ProviderUnavailableError(_NO_ANSWER_IN_TIME)
            try:
                return self._call(
                    model=self.assistant_model, contents=contents, config=config(remaining)
                )
            except DailyLimitReached:
                state["outcome"] = "daily_limit"
                raise
            except errors.APIError as error:
                code = getattr(error, "code", None)
                if code in _RETRYABLE_HTTP_CODES and state["backoff"] < len(BACKOFF_SECONDS):
                    delay = BACKOFF_SECONDS[state["backoff"]]
                    state["backoff"] += 1
                    if self._clock() + delay >= deadline:
                        state["outcome"] = "timeout"
                        raise ProviderUnavailableError(_NO_ANSWER_IN_TIME) from None
                    self._sleep(delay)
                    continue
                # The status name (e.g. INVALID_ARGUMENT) says why without echoing any content.
                status = str(getattr(error, "status", "") or "")
                state["outcome"] = (f"http_{code}" if code else "api_error") + (
                    f"_{status}" if status.replace("_", "").isalpha() else ""
                )
                raise ProviderUnavailableError("The AI provider refused the request.") from None
            except Exception:  # noqa: BLE001  (timeouts and connection errors differ per SDK)
                state["outcome"] = "network_error"
                raise ProviderUnavailableError("The AI provider could not be reached.") from None
