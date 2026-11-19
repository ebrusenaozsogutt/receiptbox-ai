"""Application settings, loaded from environment variables and an optional .env file."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_JWT_SECRET_LENGTH = 32  # HS256 needs a key of at least 256 bits

DEFAULT_MODEL_EXTRACT = "gemini-3.5-flash-lite"  # fast, generous free quota: receipts
DEFAULT_MODEL_ASSISTANT = "gemini-3.5-flash"  # P14


class Settings(BaseSettings):
    # ".env" when started from the repo root, "../.env" when started from backend/.
    # hide_input_in_errors: a rejected JWT_SECRET must not be echoed in the error message.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), extra="ignore", hide_input_in_errors=True
    )

    # Host port 5433 is the docker compose `db` service (see infra/docker-compose.yml).
    database_url: str = "postgresql+asyncpg://receiptbox:receiptbox@127.0.0.1:5433/receiptbox"
    # Used by the test-suite only; the database is created by infra/db/init-test-db.sql.
    test_database_url: str = (
        "postgresql+asyncpg://receiptbox:receiptbox@127.0.0.1:5433/receiptbox_test"
    )

    # Required: no default on purpose, so a missing secret fails loudly at start-up.
    jwt_secret: SecretStr

    storage_root: str = "./storage"

    # "gemini" (real, needs GEMINI_API_KEY) or "fake" (fixtures; used by all tests).
    ai_provider: str = "gemini"
    # Model names live here and in .env only, never in the provider code. An empty value in
    # .env means "use the default". Defaults: Gemini free-tier models checked on 2026-11-19.
    ai_model_extract: str = DEFAULT_MODEL_EXTRACT
    ai_model_assistant: str = DEFAULT_MODEL_ASSISTANT
    gemini_api_key: SecretStr = SecretStr("")
    ai_timeout_seconds: float = 30.0
    # Where FakeProvider finds its fixtures (relative to backend/ when started from there).
    ai_fake_fixtures_dir: str = "tests/fixtures/receipts"

    log_level: str = "INFO"

    @field_validator("ai_model_extract", mode="before")
    @classmethod
    def _blank_extract_model_means_default(cls, value: object) -> object:
        return value if isinstance(value, str) and value.strip() else DEFAULT_MODEL_EXTRACT

    @field_validator("ai_model_assistant", mode="before")
    @classmethod
    def _blank_assistant_model_means_default(cls, value: object) -> object:
        return value if isinstance(value, str) and value.strip() else DEFAULT_MODEL_ASSISTANT

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # jwt_secret is read from the environment
