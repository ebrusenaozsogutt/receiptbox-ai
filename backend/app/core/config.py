"""Application settings, loaded from environment variables and an optional .env file."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ".env" when started from the repo root, "../.env" when started from backend/.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Host port 5433 is the docker compose `db` service (see infra/docker-compose.yml).
    database_url: str = "postgresql+asyncpg://receiptbox:receiptbox@127.0.0.1:5433/receiptbox"
    # Used by the test-suite only; the database is created by infra/db/init-test-db.sql.
    test_database_url: str = (
        "postgresql+asyncpg://receiptbox:receiptbox@127.0.0.1:5433/receiptbox_test"
    )

    # Required: no default on purpose, so a missing secret fails loudly at start-up.
    jwt_secret: SecretStr

    storage_root: str = "./storage"

    ai_provider: str = "gemini"
    # Model names always come from the environment (set in P05); never hard-coded in code.
    ai_model_extract: str = ""
    ai_model_assistant: str = ""
    gemini_api_key: SecretStr = SecretStr("")

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # jwt_secret is read from the environment
