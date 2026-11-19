"""GeminiProvider with a stand-in for the SDK client: no network, no real model.

Covers the phase file's rules: 1 retry on invalid schema, back-off on 429, 30 s budget, model
name from settings, and logging that never contains the receipt text.
"""

import logging
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import SecretStr

from app.ai.provider import (
    ExtractionHints,
    ProviderConfigError,
    ProviderOutputError,
    ProviderUnavailableError,
    get_provider,
)
from app.ai.providers.fake import FakeProvider
from app.ai.providers.gemini import BACKOFF_SECONDS, GeminiProvider
from app.core.config import DEFAULT_MODEL_ASSISTANT, DEFAULT_MODEL_EXTRACT, Settings
from app.models.enums import CategoryKey

HINTS = ExtractionHints(capture_date=date(2026, 11, 19), source="GALLERY")
TEXT = "SECRET MARKET\nTARIH: 14.11.2026\nTOPLAM 82,40\n"
GOOD_JSON = (
    '{"merchant_raw": "SECRET MARKET", "date": "14.11.2026", "time": null, "total": "82,40", '
    '"payment_method": "UNKNOWN", "installment_count": null, "items": []}'
)


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"message": f"echo of {TEXT}"}})


class StubClient:
    """Plays back a script of answers: a string (the model's text) or an exception to raise."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        step = self._script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return SimpleNamespace(
            text=step,
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=45),
        )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(script: list[Any], **kwargs: Any) -> tuple[GeminiProvider, StubClient, list[float]]:
    client = StubClient(script)
    clock = Clock()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    provider = GeminiProvider(
        api_key="unused", model="test-model", client=client, sleep=sleep, clock=clock, **kwargs
    )
    return provider, client, sleeps


def test_a_good_answer_is_parsed_and_the_request_is_constrained() -> None:
    provider, client, sleeps = make([GOOD_JSON])

    result = provider.extract_receipt(TEXT, HINTS)

    assert result.total == "82,40"
    assert sleeps == []
    call = client.calls[0]
    assert call["model"] == "test-model"  # the name comes from the caller, not from the code
    assert call["contents"] == TEXT
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.temperature == 0.0
    assert "Copy, never compute" in config.system_instruction
    assert config.response_schema.__name__ == "RawReceiptExtraction"
    assert config.thinking_config is None  # not set unless the settings ask for it


def test_the_thinking_level_comes_from_the_settings_and_is_passed_on() -> None:
    provider, client, _ = make([GOOD_JSON], thinking_level="MINIMAL")

    provider.extract_receipt(TEXT, HINTS)

    assert str(client.calls[0]["config"].thinking_config.thinking_level).endswith("MINIMAL")


def test_an_empty_thinking_level_setting_means_the_model_default() -> None:
    provider = get_provider(
        settings(
            ai_provider="gemini",
            gemini_api_key=SecretStr("not-a-real-key"),
            ai_thinking_level="  ",
        )
    )
    assert provider._thinking is None


def test_an_invalid_answer_is_retried_once() -> None:
    provider, client, _ = make(["not json at all", GOOD_JSON])

    assert provider.extract_receipt(TEXT, HINTS).merchant_raw == "SECRET MARKET"
    assert len(client.calls) == 2


def test_an_answer_that_breaks_the_schema_is_retried_once() -> None:
    wrong_types = '{"merchant_raw": 5, "items": "none"}'
    provider, client, _ = make([wrong_types, GOOD_JSON])

    provider.extract_receipt(TEXT, HINTS)

    assert len(client.calls) == 2


def test_two_invalid_answers_in_a_row_fail() -> None:
    provider, client, _ = make(["nope", "still nope"])

    with pytest.raises(ProviderOutputError):
        provider.extract_receipt(TEXT, HINTS)

    assert len(client.calls) == 2  # one retry, not more


def test_429_is_retried_with_exponential_backoff() -> None:
    provider, client, sleeps = make([api_error(429), api_error(429), GOOD_JSON])

    provider.extract_receipt(TEXT, HINTS)

    assert sleeps == [1.0, 2.0]
    assert len(client.calls) == 3


def test_429_that_never_stops_gives_up_after_the_backoff_steps() -> None:
    provider, client, sleeps = make([api_error(429)] * 4)

    with pytest.raises(ProviderUnavailableError):
        provider.extract_receipt(TEXT, HINTS)

    assert tuple(sleeps) == BACKOFF_SECONDS
    assert len(client.calls) == len(BACKOFF_SECONDS) + 1


def test_server_errors_are_retried_but_client_errors_are_not() -> None:
    provider, client, sleeps = make([api_error(503), GOOD_JSON])
    provider.extract_receipt(TEXT, HINTS)
    assert sleeps == [1.0]

    provider, client, sleeps = make([api_error(400), GOOD_JSON])
    with pytest.raises(ProviderUnavailableError):
        provider.extract_receipt(TEXT, HINTS)
    assert sleeps == []
    assert len(client.calls) == 1


def test_the_time_budget_stops_the_retries() -> None:
    provider, client, sleeps = make([api_error(429)] * 4, timeout_seconds=2.5)

    with pytest.raises(ProviderUnavailableError):
        provider.extract_receipt(TEXT, HINTS)

    assert sleeps == [1.0]  # 1 s fits in the 2.5 s budget; waiting 2 s more would not
    assert len(client.calls) == 2


def test_each_request_gets_the_remaining_time_as_its_timeout() -> None:
    provider, client, _ = make([api_error(429), GOOD_JSON], timeout_seconds=30.0)

    provider.extract_receipt(TEXT, HINTS)

    first, second = (call["config"].http_options.timeout for call in client.calls)
    assert first == 30_000
    assert second == 29_000


def test_a_network_failure_becomes_a_provider_error_without_the_original_message() -> None:
    provider, _, _ = make([ConnectionError(f"could not reach host for {TEXT}")])

    with pytest.raises(ProviderUnavailableError) as raised:
        provider.extract_receipt(TEXT, HINTS)

    assert "SECRET" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_sdk_error_messages_that_echo_the_request_never_leave_the_provider() -> None:
    provider, _, _ = make([api_error(400)])

    with pytest.raises(ProviderUnavailableError) as raised:
        provider.extract_receipt(TEXT, HINTS)

    assert "SECRET" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_every_call_is_logged_with_metadata_and_never_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _, _ = make([api_error(429), GOOD_JSON])

    with caplog.at_level(logging.INFO, logger="receiptbox.ai"):
        provider.extract_receipt(TEXT, HINTS)

    (record,) = [r for r in caplog.records if r.name == "receiptbox.ai"]
    assert record.provider == "gemini"
    assert record.model == "test-model"
    assert record.prompt_version == "receipt_extract.v1"
    assert record.input_tokens == 120
    assert record.output_tokens == 45
    assert record.outcome == "ok"
    assert isinstance(record.latency_ms, int)
    everything = repr(record.__dict__)
    for secret in ("SECRET", "82,40", "14.11.2026"):
        assert secret not in everything


def test_a_failed_call_is_logged_too(caplog: pytest.LogCaptureFixture) -> None:
    provider, _, _ = make([api_error(400)])

    with (
        caplog.at_level(logging.INFO, logger="receiptbox.ai"),
        pytest.raises(ProviderUnavailableError),
    ):
        provider.extract_receipt(TEXT, HINTS)

    (record,) = [r for r in caplog.records if r.name == "receiptbox.ai"]
    assert record.outcome == "http_400"


def test_a_category_answer_is_parsed_and_constrained_to_the_enum() -> None:
    provider, client, _ = make(["FUEL"])

    key = provider.classify_category("OPET", ["KURSUNSUZ 95"])

    assert key == CategoryKey.FUEL
    call = client.calls[0]
    assert call["contents"] == "Merchant: OPET\nItems: KURSUNSUZ 95"
    config = call["config"]
    assert config.response_mime_type == "text/x.enum"
    assert config.response_schema is CategoryKey
    assert "ONE spending category" in config.system_instruction


def test_a_category_answer_with_quotes_or_spaces_is_accepted() -> None:
    provider, _, _ = make(['  "GROCERY"\n'])
    assert provider.classify_category("X", []) == CategoryKey.GROCERY


def test_an_unknown_category_word_is_retried_once_then_fails() -> None:
    provider, client, _ = make(["Market", "Gıda"])

    with pytest.raises(ProviderOutputError):
        provider.classify_category("X", [])

    assert len(client.calls) == 2


def test_an_unknown_category_word_then_a_good_one_succeeds() -> None:
    provider, client, _ = make(["Market", "GROCERY"])

    assert provider.classify_category("X", []) == CategoryKey.GROCERY
    assert len(client.calls) == 2


def test_classification_sends_no_items_line_when_there_are_none_and_caps_long_lists() -> None:
    provider, client, _ = make(["OTHER", "OTHER"])

    provider.classify_category("", [])
    provider.classify_category("M", [f"item{n}" for n in range(50)])

    assert client.calls[0]["contents"] == "Merchant: (unknown)"
    assert client.calls[1]["contents"].count("item") == 20


def test_classification_is_logged_with_its_own_prompt_version(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _, _ = make(["FUEL"])

    with caplog.at_level(logging.INFO, logger="receiptbox.ai"):
        provider.classify_category("SECRET SHOP", ["SECRET ITEM"])

    (record,) = [r for r in caplog.records if r.name == "receiptbox.ai"]
    assert record.prompt_version == "category_classify.v1"
    assert "SECRET" not in repr(record.__dict__)


def test_classification_failures_are_provider_errors() -> None:
    provider, _, _ = make([api_error(400)])
    with pytest.raises(ProviderUnavailableError):
        provider.classify_category("X", [])


def test_the_other_methods_are_not_implemented_yet() -> None:
    provider, _, _ = make([])
    with pytest.raises(NotImplementedError):
        provider.extract_bank_rows("x", None)
    with pytest.raises(NotImplementedError):
        provider.run_assistant([], [], None)


# ---- configuration ---------------------------------------------------------------------------


def settings(**overrides: Any) -> Settings:
    base = Settings()  # type: ignore[call-arg]
    return base.model_copy(update=overrides)


def test_tests_are_forced_onto_the_fake_provider_and_have_no_api_key() -> None:
    current = Settings()  # type: ignore[call-arg]
    assert current.ai_provider == "fake"
    assert current.gemini_api_key.get_secret_value() == ""
    assert isinstance(get_provider(current), FakeProvider)


def test_the_gemini_provider_takes_model_and_key_from_settings() -> None:
    provider = get_provider(
        settings(
            ai_provider="gemini",
            gemini_api_key=SecretStr("not-a-real-key"),
            ai_model_extract="some-model-name",
            ai_timeout_seconds=12.0,
        )
    )

    assert isinstance(provider, GeminiProvider)
    assert provider.model == "some-model-name"
    assert provider._timeout_seconds == 12.0


def test_gemini_without_a_key_is_a_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        get_provider(settings(ai_provider="gemini", gemini_api_key=SecretStr("")))


def test_an_unknown_provider_name_is_a_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        get_provider(settings(ai_provider="something-else"))


def test_blank_model_names_fall_back_to_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_EXTRACT", "")
    monkeypatch.setenv("AI_MODEL_ASSISTANT", "   ")

    current = Settings()  # type: ignore[call-arg]

    assert current.ai_model_extract == DEFAULT_MODEL_EXTRACT
    assert current.ai_model_assistant == DEFAULT_MODEL_ASSISTANT


def test_model_names_from_the_environment_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_EXTRACT", "my-extract-model")

    assert Settings().ai_model_extract == "my-extract-model"  # type: ignore[call-arg]
