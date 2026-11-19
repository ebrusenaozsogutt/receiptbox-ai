"""ExtractionService: provider -> validation -> observation rows (database, rolled back)."""

import re
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderOutputError, ProviderUnavailableError
from app.ai.providers.fake import FakeProvider
from app.ai.schemas import RawReceiptExtraction, RawReceiptItem
from app.core.errors import (
    ExtractionFailedError,
    ExtractionRejectedError,
    NotFoundError,
    TextTooLargeError,
)
from app.models import Observation, ReceiptItem
from app.models.enums import Direction, ObservationSource, ObservationStatus
from app.repositories.observations import ObservationRepository
from app.services.extraction_service import (
    MAX_TEXT_BYTES,
    ExtractionService,
    compute_fingerprint,
)
from tests.conftest import create_user

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "receipts"
TODAY = date(2026, 11, 19)
CAPTURE = date(2026, 11, 18)


def read(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")


def service(session: AsyncSession, provider: object | None = None) -> ExtractionService:
    chosen = provider or FakeProvider.from_directory(FIXTURE_DIR)
    return ExtractionService(session, chosen, today=TODAY)  # type: ignore[arg-type]


async def extract(svc: ExtractionService, user_id: uuid.UUID, name: str = "01_migros"):  # noqa: ANN201
    return await svc.extract_receipt(
        user_id, masked_text=read(name), capture_date=CAPTURE, source="GALLERY"
    )


async def test_a_receipt_becomes_a_pending_review_observation(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    outcome = await extract(service(db_session), user.id)

    observation = await db_session.get(Observation, outcome.observation_id)
    assert observation is not None
    assert observation.user_id == user.id
    assert observation.source == ObservationSource.RECEIPT
    assert observation.status == ObservationStatus.PENDING_REVIEW
    assert observation.direction == Direction.DEBIT
    assert observation.merchant_raw == "MIGROS TICARET A.S."
    assert observation.amount_minor == 27030  # integer kuruş, never a float
    assert observation.obs_date == date(2026, 11, 14)
    assert str(observation.obs_time) == "18:42:00"
    assert observation.installment_count is None
    assert observation.transaction_id is None  # evidence only: no transaction yet
    assert observation.masked_text == read("01_migros")


async def test_confidence_extraction_and_prompt_version_are_saved(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)

    outcome = await extract(service(db_session), user.id, "08_yanlis_kalem_toplami")

    observation = await db_session.get(Observation, outcome.observation_id)
    assert observation is not None
    assert observation.field_confidence_json["items"] == "LOW"
    assert observation.field_confidence_json["total"] == "HIGH"
    saved = observation.extraction_json
    assert saved["extraction"]["total"] == "165.00"
    assert saved["issues"] == ["items_sum_mismatch"]
    assert saved["meta"] == {
        "ai_used": True,
        "provider": "fake",
        "model": "fake-fixtures",
        "prompt_version": "receipt_extract.v1",
    }
    assert saved["llm_output"]["items"][2]["total_price"] == "102,00"  # what the model said


async def test_items_are_saved_in_kurus_and_discount_lines_are_not(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)

    outcome = await extract(service(db_session), user.id, "03_a101_indirim")

    items = (
        (
            await db_session.execute(
                select(ReceiptItem).where(ReceiptItem.observation_id == outcome.observation_id)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(i.name_raw for i in items) == [
        "DETERJAN 3KG",
        "PEYNIR BEYAZ 500G",
        "YUMURTA 15 LI",
    ]
    assert sorted(i.total_price_minor for i in items if i.total_price_minor) == [7990, 9495, 18950]
    assert all(i.total_price_minor >= 0 for i in items if i.total_price_minor is not None)


async def test_quantity_defaults_to_one_when_the_receipt_prints_none(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)

    outcome = await extract(service(db_session), user.id, "02_bim")

    rows = (
        await db_session.execute(
            text(
                "SELECT name_raw, quantity, unit_price_minor FROM receipt_items "
                "WHERE observation_id = :id ORDER BY name_raw"
            ),
            {"id": outcome.observation_id},
        )
    ).all()
    by_name = {row[0]: (str(row[1]), row[2]) for row in rows}
    assert by_name["YOGURT 1KG"] == ("1.000", None)
    assert by_name["DOMATES KG"] == ("0.850", 4490)
    assert by_name["MAKARNA 500G"] == ("2.000", 1225)


async def test_a_receipt_without_a_date_is_saved_with_a_null_date(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    outcome = await extract(service(db_session), user.id, "07_tarihsiz")

    observation = await db_session.get(Observation, outcome.observation_id)
    assert observation is not None
    assert observation.obs_date is None
    assert observation.field_confidence_json["date"] == "LOW"
    assert outcome.extraction.date is None


async def test_an_absurd_amount_is_rejected_and_nothing_is_saved(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    with pytest.raises(ExtractionRejectedError):
        await extract(service(db_session), user.id, "12_absurd_tutar")

    assert await ObservationRepository(db_session).count(user.id) == 0


async def test_a_provider_failure_saves_nothing_and_hides_the_cause(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)

    class Failing(FakeProvider):
        def extract_receipt(self, masked_text, hints):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("could not reach SECRET HOST")

    with pytest.raises(ExtractionFailedError) as raised:
        await extract(service(db_session, Failing()), user.id)

    assert "SECRET" not in raised.value.message
    assert raised.value.__cause__ is None
    assert await ObservationRepository(db_session).count(user.id) == 0


async def test_a_text_without_a_fixture_is_a_provider_error(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    with pytest.raises(ExtractionFailedError):
        await service(db_session).extract_receipt(
            user.id, masked_text="UNKNOWN RECEIPT 12,00", capture_date=CAPTURE, source="CAMERA"
        )
    with pytest.raises(ProviderOutputError):
        FakeProvider().extract_receipt("anything", None)  # type: ignore[arg-type]


async def test_text_over_20_kb_is_refused_before_the_provider_is_called(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    provider = FakeProvider()

    with pytest.raises(TextTooLargeError):
        await service(db_session, provider).extract_receipt(
            user.id, masked_text="A" * (MAX_TEXT_BYTES + 1), capture_date=CAPTURE, source="CAMERA"
        )

    assert provider.calls == 0


async def test_20_kb_exactly_is_accepted(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    padded = "KOSE MANAV\n" + "X" * (MAX_TEXT_BYTES - len("KOSE MANAV\n"))
    assert len(padded.encode("utf-8")) == MAX_TEXT_BYTES
    provider = FakeProvider()
    provider.add(
        padded,
        RawReceiptExtraction(
            merchant_raw="KOSE MANAV",
            date=None,
            time=None,
            total=None,
            payment_method="UNKNOWN",
            installment_count=None,
            items=[],
        ),
    )

    outcome = await service(db_session, provider).extract_receipt(
        user.id, masked_text=padded, capture_date=CAPTURE, source="CAMERA"
    )

    assert outcome.extraction.total is None  # nothing readable: saved with an empty amount


async def test_the_size_limit_counts_bytes_not_characters(db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    with pytest.raises(TextTooLargeError):
        await service(db_session).extract_receipt(
            user.id,
            masked_text="Ş" * (MAX_TEXT_BYTES // 2 + 1),  # 2 bytes each in UTF-8
            capture_date=CAPTURE,
            source="CAMERA",
        )


async def test_observations_are_scoped_to_their_owner(db_session: AsyncSession) -> None:
    owner = await create_user(db_session, "owner")
    other = await create_user(db_session, "other")
    outcome = await extract(service(db_session), owner.id)
    repository = ObservationRepository(db_session)

    assert await repository.get(owner.id, outcome.observation_id) is not None
    assert await repository.get(other.id, outcome.observation_id) is None
    assert await repository.count(other.id) == 0
    with pytest.raises(NotFoundError):  # an item cannot be attached to someone else's row
        await repository.add_receipt_item(
            other.id,
            outcome.observation_id,
            name_raw="X",
            quantity=1,  # type: ignore[arg-type]
            unit_price_minor=None,
            total_price_minor=None,
        )


async def test_the_same_receipt_twice_gets_the_same_fingerprint(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    svc = service(db_session)

    first = await extract(svc, user.id)
    second = await extract(svc, user.id)

    a = await db_session.get(Observation, first.observation_id)
    b = await db_session.get(Observation, second.observation_id)
    assert a is not None and b is not None
    assert a.id != b.id
    assert re.fullmatch(r"[0-9a-f]{64}", a.fingerprint)
    assert a.fingerprint == b.fingerprint  # P09 will mark the second one as a duplicate


def test_the_fingerprint_follows_the_formula_of_spec_7_2() -> None:
    base = {
        "source": "RECEIPT",
        "merchant_raw": "Migros Ticaret A.Ş.",
        "amount_minor": 27030,
        "obs_date": date(2026, 11, 14),
        "obs_time": "18:42:00",
    }
    same_merchant_other_spelling = {**base, "merchant_raw": "MİGROS TİCARET AŞ"}
    assert compute_fingerprint(**base) == compute_fingerprint(**same_merchant_other_spelling)
    for change in (
        {"source": "MANUAL"},
        {"amount_minor": 27031},
        {"obs_date": date(2026, 11, 15)},
        {"obs_time": None},
        {"merchant_raw": "BIM"},
        {"installment_seq": 2},
    ):
        assert compute_fingerprint(**base) != compute_fingerprint(**{**base, **change})
    assert compute_fingerprint(
        source="RECEIPT", merchant_raw=None, amount_minor=None, obs_date=None, obs_time=None
    )


def test_receipt_item_model_matches_what_the_service_writes() -> None:
    item = RawReceiptItem(name_raw="A", quantity=None, unit_price=None, total_price="1,00")
    assert item.total_price == "1,00"
