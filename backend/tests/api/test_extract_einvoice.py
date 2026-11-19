"""POST /api/v1/extract/einvoice-qr and the merchant / category suggestions of both endpoints.
All payloads are synthetic. FakeProvider only: the call counters prove when the AI was used."""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.ai.schemas import RawReceiptExtraction, RawReceiptItem
from app.models.enums import CategoryKey
from app.services import extraction_service
from tests.auth_helpers import bearer, fetch_all, register_ok

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "receipts"
URL = "/api/v1/extract/einvoice-qr"
RECEIPT_URL = "/api/v1/extract/receipt"
TODAY = date(2026, 11, 19)
ETTN = "11111111-2222-3333-4444-555555555555"
BUYER_TCKN = "12345678901"
SELLER_VKN = "1234567890"

INVOICE_TEXT = (
    "ORNEK ELEKTRONIK TICARET A.S.\n"
    "e-Arsiv Fatura\n"
    "Fatura No: ABC2026000000123\n"
    "Tarih: 14-11-2026\n"
    "KULAKLIK BLUETOOTH      2.118,64\n"
    "KDV %18                   380,36\n"
    "ODENECEK TUTAR         2.499,00\n"
)


def qr(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ettn": ETTN,
        "vkntckn": SELLER_VKN,
        "senaryo": "EARSIVFATURA",
        "tarih": "14-11-2026",
        "no": "ABC2026000000123",
        "parabirimi": "TRY",
        "malhizmettoplam": "2118.64",
        "vergidahil": "2499.00",
        "odenecek": "2499.00",
    }
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


def body(payload: object | None = None, **extra: object) -> dict[str, object]:
    return {
        "qr_payload": payload if payload is not None else qr(),
        "capture_date": "2026-11-18",
        **extra,
    }


def invoice_answer(**changes: object) -> RawReceiptExtraction:
    values: dict[str, object] = {
        "merchant_raw": "ORNEK ELEKTRONIK TICARET A.S.",
        "date": "14-11-2026",
        "time": None,
        "total": "2.499,00",
        "payment_method": "UNKNOWN",
        "installment_count": None,
        "items": [
            RawReceiptItem(
                name_raw="KULAKLIK BLUETOOTH",
                quantity=None,
                unit_price=None,
                total_price="2.118,64",
            ),
            RawReceiptItem(
                name_raw="KDV %18", quantity=None, unit_price=None, total_price="380,36"
            ),
        ],
    }
    values.update(changes)
    return RawReceiptExtraction(**values)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_service, "business_today", lambda: TODAY)


@pytest.fixture
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(FIXTURE_DIR)
    fake.add(INVOICE_TEXT, invoice_answer())
    fake.add_category("ORNEK ELEKTRONIK TICARET A.S.", CategoryKey.TECHNOLOGY)
    api_app.state.ai_provider = fake
    return fake


async def user(client: AsyncClient, *, consent: bool) -> dict[str, str]:
    headers = bearer((await register_ok(client))["access_token"])
    if consent:
        await client.put("/api/v1/me/ai-consent", json={"ai_consent": True}, headers=headers)
    return headers


# ---- a QR-only invoice: no AI at all ---------------------------------------------------------


async def test_a_qr_only_invoice_creates_an_observation_without_any_llm_call(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(URL, json=body(), headers=headers)

    assert response.status_code == 200, response.text
    assert (provider.calls, provider.classify_calls) == (0, 0)  # the phase's acceptance test
    result = response.json()
    assert result["ai_used"] is False
    assert result["extraction"]["total"] == "2499.00"
    assert result["extraction"]["date"] == "2026-11-14"
    assert result["extraction"]["currency"] == "TRY"
    assert result["confidence"]["total"] == "HIGH"
    assert result["confidence"]["date"] == "HIGH"
    assert result["confidence"]["merchant"] == "LOW"  # the QR has no merchant name
    rows = await fetch_all(
        api_app,
        "SELECT source, status, amount_minor, external_id, obs_date, merchant_raw, masked_text "
        "FROM observations WHERE id = :id",
        id=result["observation_id"],
    )
    source, status, amount, external_id, obs_date, merchant, masked = rows[0]
    assert (source, status, amount, external_id) == ("EINVOICE_QR", "PENDING_REVIEW", 249900, ETTN)
    assert obs_date == date(2026, 11, 14)
    assert merchant is None and masked is None


async def test_a_qr_only_invoice_needs_no_ai_consent(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=False)

    response = await api_client.post(URL, json=body(), headers=headers)

    assert response.status_code == 200
    assert response.json()["ai_used"] is False
    assert provider.calls == 0


async def test_the_qr_suggestions_say_so_when_there_is_nothing_to_suggest(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    suggestions = (await api_client.post(URL, json=body(), headers=headers)).json()["suggestions"]

    assert suggestions["merchant"]["match"] == "NONE"
    assert suggestions["category"] == {"key": "OTHER", "source": "FALLBACK"}


# ---- with the invoice text -------------------------------------------------------------------


async def test_with_text_and_consent_the_ai_adds_merchant_and_items_but_the_qr_keeps_the_header(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(URL, json=body(masked_text=INVOICE_TEXT), headers=headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ai_used"] is True
    assert provider.calls == 1
    extraction = result["extraction"]
    assert extraction["merchant_raw"] == "ORNEK ELEKTRONIK TICARET A.S."
    assert [item["name_raw"] for item in extraction["items"]] == ["KULAKLIK BLUETOOTH", "KDV %18"]
    assert extraction["total"] == "2499.00" and extraction["date"] == "2026-11-14"
    assert result["confidence"]["merchant"] == "HIGH"
    assert result["confidence"]["items"] == "HIGH"  # checked against the QR total
    assert result["suggestions"]["merchant"]["match"] == "NEW"
    assert result["suggestions"]["category"] == {"key": "TECHNOLOGY", "source": "LLM"}
    rows = await fetch_all(
        api_app, "SELECT masked_text FROM observations WHERE id = :id", id=result["observation_id"]
    )
    assert rows[0][0] == INVOICE_TEXT


async def test_without_consent_the_text_is_ignored_and_nothing_is_sent(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=False)

    response = await api_client.post(URL, json=body(masked_text=INVOICE_TEXT), headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result["ai_used"] is False
    assert (provider.calls, provider.classify_calls) == (0, 0)
    assert result["extraction"]["merchant_raw"] is None and result["extraction"]["items"] == []
    saved = await fetch_all(
        api_app,
        "SELECT masked_text, extraction_json FROM observations WHERE id = :id",
        id=result["observation_id"],
    )
    assert saved[0][0] is None  # the text was not even stored
    assert "text_ignored_no_consent" in saved[0][1]["issues"]


async def test_when_the_text_says_a_different_total_the_qr_wins_and_it_is_noted(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    text = INVOICE_TEXT.replace("2.499,00", "2.599,00")
    provider.add(text, invoice_answer(total="2.599,00"))
    headers = await user(api_client, consent=True)

    result = (await api_client.post(URL, json=body(masked_text=text), headers=headers)).json()

    assert result["extraction"]["total"] == "2499.00"
    assert result["confidence"]["total"] == "HIGH"
    saved = await fetch_all(
        api_app,
        "SELECT extraction_json FROM observations WHERE id = :id",
        id=result["observation_id"],
    )
    assert "llm_total_differs_from_qr" in saved[0][0]["issues"]
    # The items are judged against the QR total: they add up to it, so they are HIGH even
    # though the model's own total was wrong.
    assert result["confidence"]["items"] == "HIGH"


async def test_when_the_ai_is_down_the_qr_is_still_saved(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(
        URL, json=body(masked_text="UNKNOWN INVOICE TEXT 1,00"), headers=headers
    )

    assert response.status_code == 200
    assert response.json()["ai_used"] is False
    assert response.json()["extraction"]["total"] == "2499.00"


# ---- privacy: the buyer's identity number ---------------------------------------------------


async def test_the_buyers_tckn_is_never_stored_even_if_a_client_sends_it(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(
        URL, json=body(qr(avkntckn=BUYER_TCKN, AVKNTCKN=BUYER_TCKN)), headers=headers
    )

    assert response.status_code == 200
    assert BUYER_TCKN not in response.text
    rows = await fetch_all(api_app, "SELECT to_jsonb(observations)::text FROM observations")
    assert BUYER_TCKN not in rows[0][0]
    assert SELLER_VKN not in rows[0][0]  # the seller's number is only used for the lookup


async def test_only_whitelisted_qr_fields_are_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    await api_client.post(URL, json=body(qr(gizli="X", baska={"a": 1})), headers=headers)

    saved = (await fetch_all(api_app, "SELECT extraction_json FROM observations"))[0][0]
    assert set(saved["qr"]) <= {
        "senaryo", "tip", "no", "ettn", "tarih", "parabirimi",
        "malhizmettoplam", "vergidahil", "odenecek",
    }  # fmt: skip


# ---- errors ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    ["not json", "{broken", {"wifi": "x"}, {}, {"ettn": ETTN}, qr(parabirimi="USD")],
)
async def test_an_unusable_qr_is_422_qr_invalid(
    payload: object, api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(URL, json=body(payload), headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "QR_INVALID"
    assert "wifi" not in response.text and "broken" not in response.text
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


@pytest.mark.parametrize("odenecek", ["0,00", "1.245.000,00"])
async def test_an_absurd_qr_amount_is_rejected(
    odenecek: str, api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    response = await api_client.post(
        URL, json=body(qr(odenecek=odenecek, vergidahil=None)), headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACTION_REJECTED"
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


async def test_the_qr_payload_may_be_json_text(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=False)

    response = await api_client.post(URL, json=body(json.dumps(qr())), headers=headers)

    assert response.status_code == 200
    assert response.json()["extraction"]["total"] == "2499.00"


async def test_a_huge_payload_or_text_is_413(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)

    big_qr = await api_client.post(URL, json=body(qr(no="x" * 30_000)), headers=headers)
    big_text = await api_client.post(
        URL, json=body(masked_text="A" * (20 * 1024 + 1)), headers=headers
    )

    assert big_qr.status_code == 413 and big_text.status_code == 413


async def test_without_a_token_it_is_401(api_client: AsyncClient, provider: FakeProvider) -> None:
    response = await api_client.post(URL, json=body())

    assert response.status_code == 401


async def test_the_qr_endpoint_shares_the_20_per_minute_limit(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=False)

    for _ in range(20):
        assert (await api_client.post(URL, json=body(), headers=headers)).status_code == 200
    response = await api_client.post(URL, json=body(), headers=headers)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_the_same_invoice_twice_has_the_same_fingerprint_from_the_ettn(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=False)

    await api_client.post(URL, json=body(), headers=headers)
    await api_client.post(URL, json=body(qr(odenecek="1,00")), headers=headers)  # same ETTN

    fingerprints = [r[0] for r in await fetch_all(api_app, "SELECT fingerprint FROM observations")]
    assert len(fingerprints) == 2 and fingerprints[0] == fingerprints[1]  # P09 marks the duplicate


# ---- suggestions on the receipt endpoint ------------------------------------------------------


async def test_a_known_merchant_is_suggested_with_its_default_category_and_no_model_call(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)
    text = (FIXTURE_DIR / "01_migros.txt").read_text(encoding="utf-8")

    result = (
        await api_client.post(
            RECEIPT_URL,
            json={"masked_text": text, "capture_date": "2026-11-18", "source": "GALLERY"},
            headers=headers,
        )
    ).json()

    merchant = result["suggestions"]["merchant"]
    assert (merchant["match"], merchant["canonical_name"]) == ("GLOBAL_ALIAS", "Migros")
    assert merchant["merchant_id"] is not None
    assert result["suggestions"]["category"] == {"key": "GROCERY", "source": "MERCHANT_DEFAULT"}
    assert provider.classify_calls == 0


async def test_an_unknown_merchant_is_new_and_the_model_picks_the_category(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)
    text = (FIXTURE_DIR / "05_eczane.txt").read_text(encoding="utf-8")
    merchants_before = await fetch_all(api_app, "SELECT count(*) FROM merchants")

    result = (
        await api_client.post(
            RECEIPT_URL,
            json={"masked_text": text, "capture_date": "2026-11-18", "source": "GALLERY"},
            headers=headers,
        )
    ).json()

    assert result["suggestions"]["merchant"]["match"] == "NEW"
    assert result["suggestions"]["merchant"]["canonical_name"] == "Sifa Eczanesi"
    assert result["suggestions"]["merchant"]["merchant_id"] is None
    assert result["suggestions"]["category"] == {"key": "HEALTH_CARE", "source": "LLM"}
    assert await fetch_all(api_app, "SELECT count(*) FROM merchants") == merchants_before
    saved = await fetch_all(
        api_app,
        "SELECT extraction_json -> 'suggestions' FROM observations WHERE id = :id",
        id=result["observation_id"],
    )
    assert saved[0][0]["category"]["key"] == "HEALTH_CARE"


async def test_a_failing_classification_never_fails_the_extraction(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)
    text = "BILINMEYEN DUKKAN\nTARIH: 12.11.2026\nURUN 50,00\nTOPLAM 50,00\nNAKIT 50,00\n"
    provider.add(
        text,
        RawReceiptExtraction(
            merchant_raw="BILINMEYEN DUKKAN", date="12.11.2026", time=None, total="50,00",
            payment_method="CASH", installment_count=None,
            items=[
                RawReceiptItem(name_raw="URUN", quantity=None, unit_price=None, total_price="50,00")
            ],
        ),
    )  # fmt: skip

    response = await api_client.post(
        RECEIPT_URL,
        json={"masked_text": text, "capture_date": "2026-11-18", "source": "CAMERA"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["suggestions"]["category"] == {"key": "OTHER", "source": "FALLBACK"}


async def test_the_fingerprint_uses_the_canonical_merchant_name(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    headers = await user(api_client, consent=True)
    text = (FIXTURE_DIR / "01_migros.txt").read_text(encoding="utf-8")
    await api_client.post(
        RECEIPT_URL,
        json={"masked_text": text, "capture_date": "2026-11-18", "source": "GALLERY"},
        headers=headers,
    )

    stored = (await fetch_all(api_app, "SELECT fingerprint FROM observations"))[0][0]

    expected = extraction_service.compute_fingerprint(
        source="RECEIPT", merchant_raw="Migros", amount_minor=27030,
        obs_date=date(2026, 11, 14), obs_time="18:42:00",
    )  # fmt: skip
    assert stored == expected
