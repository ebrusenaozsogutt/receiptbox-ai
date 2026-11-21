"""Bank rows from the Gemini wrapper (with a stand-in client), the bank prompts, and the 30-day
cleanup of masked screenshot text (P08). No network, no real model."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import BANK_ROWS, load_bank_prompt, load_prompt
from app.ai.provider import ProviderOutputError
from app.ai.schemas import RawBankExtraction
from app.services.retention import MASKED_TEXT_RETENTION, null_old_masked_text
from tests.conftest import create_user
from tests.test_gemini_provider import make

SCREEN = "SECRET SHOP ISTANBUL\n12.11.2026  1.234,56 TL\n"
GOOD_ROWS = json.dumps(
    {
        "rows": [
            {
                "merchant_raw": "SECRET SHOP ISTANBUL",
                "amount_text": "1.234,56 TL",
                "date_text": "12.11.2026",
                "time": None,
                "installment_text": None,
                "is_pending": False,
            }
        ]
    }
)


class TestPrompts:
    def test_the_general_prompt_stays_the_same_for_unseen_banks(self) -> None:
        base = load_prompt(BANK_ROWS)
        for bank in (None, "", "qnb", "ziraat", "unknown"):
            assert load_bank_prompt(bank) == base

    @pytest.mark.parametrize(
        ("bank", "marker"),
        [("garanti", "Garanti BBVA"), ("kuveyt", "Kuveyt Türk"), ("akbank", "Akbank")],
    )
    def test_a_supported_bank_adds_its_hints(self, bank: str, marker: str) -> None:
        prompt = load_bank_prompt(bank)
        assert prompt.startswith(load_prompt(BANK_ROWS))
        assert f"## Bank hints: {marker}" in prompt

    def test_a_hint_can_not_reach_another_file(self) -> None:
        assert load_bank_prompt("../receipt_extract.v1") == load_prompt(BANK_ROWS)

    def test_the_prompt_says_copy_never_compute(self) -> None:
        assert "Copy, never compute" in load_prompt(BANK_ROWS)


class TestGeminiBankRows:
    def test_rows_come_back_as_text_rows(self) -> None:
        provider, client, _ = make([GOOD_ROWS])

        rows = provider.extract_bank_rows(SCREEN, "garanti")

        assert [r.merchant_raw for r in rows] == ["SECRET SHOP ISTANBUL"]
        assert rows[0].amount_text == "1.234,56 TL"
        call = client.calls[0]
        assert call["contents"] == SCREEN
        assert call["config"].response_schema is RawBankExtraction
        assert call["config"].temperature == 0.0

    def test_a_supported_bank_gets_its_hints_and_an_unseen_one_does_not(self) -> None:
        provider, client, _ = make([GOOD_ROWS, GOOD_ROWS])

        provider.extract_bank_rows(SCREEN, "garanti")
        provider.extract_bank_rows(SCREEN, None)

        with_hints = client.calls[0]["config"].system_instruction
        without = client.calls[1]["config"].system_instruction
        assert "Garanti BBVA" in with_hints
        assert "Garanti BBVA" not in without
        assert with_hints.startswith(without)

    def test_an_invalid_answer_is_retried_once_then_fails(self) -> None:
        provider, client, _ = make(["not json", "still not json"])

        with pytest.raises(ProviderOutputError):
            provider.extract_bank_rows(SCREEN, None)

        assert len(client.calls) == 2

    def test_the_log_has_no_screenshot_text(self, caplog: pytest.LogCaptureFixture) -> None:
        provider, _, _ = make([GOOD_ROWS])
        caplog.set_level(logging.DEBUG)

        provider.extract_bank_rows(SCREEN, "garanti")

        logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
        assert "SECRET SHOP" not in logged
        assert "1.234,56" not in logged
        assert BANK_ROWS in logged


class TestRetention:
    async def _observation(
        self, session: AsyncSession, user_id: uuid.UUID, age: timedelta, masked: str | None
    ) -> uuid.UUID:
        row = await session.execute(
            text(
                "INSERT INTO observations (user_id, source, fingerprint, masked_text, created_at) "
                "VALUES (:u, 'BANK_SCREENSHOT', :f, :m, :c) RETURNING id"
            ),
            {
                "u": user_id,
                "f": uuid.uuid4().hex,
                "m": masked,
                "c": datetime.now(UTC) - age,
            },
        )
        return row.scalar_one()

    async def _masked(self, session: AsyncSession, observation_id: uuid.UUID) -> str | None:
        row = await session.execute(
            text("SELECT masked_text FROM observations WHERE id = :i"), {"i": observation_id}
        )
        return row.scalar_one()

    async def test_text_older_than_30_days_is_removed_and_younger_text_stays(
        self, db_session: AsyncSession
    ) -> None:
        user = await create_user(db_session)
        old = await self._observation(db_session, user.id, timedelta(days=31), "OLD TEXT")
        edge = await self._observation(db_session, user.id, timedelta(days=29), "RECENT TEXT")
        fresh = await self._observation(db_session, user.id, timedelta(minutes=5), "FRESH TEXT")
        nothing = await self._observation(db_session, user.id, timedelta(days=90), None)

        removed = await null_old_masked_text(db_session)

        assert removed == 1
        assert await self._masked(db_session, old) is None
        assert await self._masked(db_session, edge) == "RECENT TEXT"
        assert await self._masked(db_session, fresh) == "FRESH TEXT"
        assert await self._masked(db_session, nothing) is None

    async def test_it_works_for_every_users_rows_and_keeps_the_fields(
        self, db_session: AsyncSession
    ) -> None:
        alice = await create_user(db_session, "alice")
        bob = await create_user(db_session, "bob")
        a = await self._observation(db_session, alice.id, timedelta(days=40), "A")
        b = await self._observation(db_session, bob.id, timedelta(days=40), "B")

        removed = await null_old_masked_text(db_session)

        assert removed >= 2
        assert await self._masked(db_session, a) is None
        assert await self._masked(db_session, b) is None
        kept = await db_session.execute(
            text("SELECT source, fingerprint FROM observations WHERE id = :i"), {"i": a}
        )
        assert kept.one()[0] == "BANK_SCREENSHOT"

    async def test_the_cutoff_is_exactly_30_days(self, db_session: AsyncSession) -> None:
        assert MASKED_TEXT_RETENTION == timedelta(days=30)
        user = await create_user(db_session)
        observation = await self._observation(db_session, user.id, timedelta(days=15), "X")

        await null_old_masked_text(db_session, now=datetime.now(UTC) + timedelta(days=16))

        assert await self._masked(db_session, observation) is None
