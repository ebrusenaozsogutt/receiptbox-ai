"""Documents: private storage, 5-minute single-document tokens, isolation between users."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.security.document_tokens import create_document_token
from app.security.tokens import create_access_token
from app.storage.backend import LocalStorage, StorageError
from tests.auth_helpers import bearer, fetch_all
from tests.conftest import make_test_settings
from tests.p07_helpers import (
    JPEG,
    PDF,
    PNG,
    Account,
    execute,
    insert_transaction,
    new_account,
    stored_files,
    upload_files,
)

URL = "/api/v1/documents"


def secret() -> str:
    return Settings().jwt_secret.get_secret_value()  # type: ignore[call-arg]


async def upload(client: AsyncClient, account: Account, data: bytes = JPEG, **fields: str) -> dict:
    response = await client.post(
        URL, files=upload_files(data), data=fields, headers=account.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---- upload ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "mime"), [(JPEG, "image/jpeg"), (PNG, "image/png"), (PDF, "application/pdf")]
)
async def test_jpeg_png_and_pdf_are_stored_privately(
    data: bytes, mime: str, api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    account = await new_account(api_client)

    document = await upload(api_client, account, data)

    assert document["mime_type"] == mime
    assert document["size_bytes"] == len(data)
    assert len(document["sha256"]) == 64
    assert document["type"] == "RECEIPT_IMAGE"
    assert document["transaction_id"] is None
    assert "storage_key" not in document and "users/" not in str(document)
    files = stored_files(storage_root / "users" / str(account.user_id))
    assert len(files) == 1 and files[0].read_bytes() == data
    rows = await fetch_all(api_app, "SELECT storage_key, mime_type FROM documents")
    assert rows[0][0] == f"users/{account.user_id}/{files[0].name}"


async def test_the_type_is_decided_from_the_bytes_not_from_what_the_client_says(
    api_client: AsyncClient, storage_root: Path
) -> None:
    account = await new_account(api_client)

    for data, name, claimed in (
        (b"MZ\x90\x00 an executable", "receipt.jpg", "image/jpeg"),
        (b"<html><script>alert(1)</script>", "receipt.png", "image/png"),
        (b"plain text", "receipt.pdf", "application/pdf"),
        (b"", "empty.jpg", "image/jpeg"),
        (b"GIF89a....", "image.gif", "image/gif"),
    ):
        response = await api_client.post(
            URL, files={"file": (name, data, claimed)}, headers=account.headers
        )
        assert response.status_code == 415, name
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert stored_files(storage_root) == []


async def test_a_pdf_with_a_jpeg_name_is_stored_as_a_pdf(api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    response = await api_client.post(
        URL, files={"file": ("sneaky.jpg", PDF, "image/jpeg")}, headers=account.headers
    )

    assert response.json()["mime_type"] == "application/pdf"


async def test_the_file_name_never_reaches_the_disk(
    api_client: AsyncClient, storage_root: Path
) -> None:
    account = await new_account(api_client)

    response = await api_client.post(
        URL, files={"file": ("../../evil.jpg", JPEG, "image/jpeg")}, headers=account.headers
    )

    assert response.status_code == 201
    assert not path_exists(storage_root.parent / "evil.jpg")
    names = [path.name for path in stored_files(storage_root)]
    assert len(names) == 1 and len(names[0]) == 32 and "evil" not in names[0]


async def test_10_mb_is_accepted_and_one_byte_more_is_413(
    api_client: AsyncClient, storage_root: Path
) -> None:
    account = await new_account(api_client)
    limit = 10 * 1024 * 1024

    ok = await api_client.post(
        URL, files=upload_files(JPEG + b"x" * (limit - len(JPEG))), headers=account.headers
    )
    too_big = await api_client.post(
        URL, files=upload_files(JPEG + b"x" * (limit - len(JPEG) + 1)), headers=account.headers
    )

    assert ok.status_code == 201
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert len(stored_files(storage_root)) == 1


async def test_the_type_field_can_mark_an_invoice(api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    document = await upload(api_client, account, PDF, type="INVOICE")

    assert document["type"] == "INVOICE"


async def test_an_unknown_document_type_is_422(api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    response = await api_client.post(
        URL, files=upload_files(JPEG), data={"type": "SELFIE"}, headers=account.headers
    )

    assert response.status_code == 422


async def test_a_document_can_be_attached_to_the_users_own_transaction(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client)
    transaction_id = await insert_transaction(api_app, account.user_id)

    document = await upload(api_client, account, transaction_id=str(transaction_id))

    assert document["transaction_id"] == str(transaction_id)


async def test_a_document_cannot_be_attached_to_someone_elses_transaction(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    owner = await new_account(api_client)
    intruder = await new_account(api_client)
    transaction_id = await insert_transaction(api_app, owner.user_id)

    response = await api_client.post(
        URL,
        files=upload_files(JPEG),
        data={"transaction_id": str(transaction_id)},
        headers=intruder.headers,
    )

    assert response.status_code == 404
    assert await fetch_all(api_app, "SELECT id FROM documents") == []
    assert stored_files(storage_root) == []


async def test_an_unknown_or_deleted_transaction_is_404(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client)
    deleted = await insert_transaction(api_app, account.user_id)
    await execute(api_app, "UPDATE transactions SET deleted_at = now() WHERE id = :id", id=deleted)

    for transaction_id in (uuid.uuid4(), deleted):
        response = await api_client.post(
            URL,
            files=upload_files(JPEG),
            data={"transaction_id": str(transaction_id)},
            headers=account.headers,
        )
        assert response.status_code == 404


# ---- access tokens ---------------------------------------------------------------------------


async def test_a_token_opens_the_document_without_an_authorization_header(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account, PNG)

    token = await api_client.post(f"{URL}/{document['id']}/access-token", headers=account.headers)
    assert token.status_code == 200
    assert token.json()["expires_in"] == 300
    url = token.json()["content_url"]
    assert url == f"/documents/{document['id']}/content?token={token.json()['token']}"

    content = await api_client.get(f"/api/v1{url}")  # no Authorization header at all

    assert content.status_code == 200
    assert content.content == PNG
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.headers["cache-control"] == "private, no-store"


async def test_the_token_lives_5_minutes(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)
    just_valid = create_document_token(
        account.user_id,
        uuid.UUID(document["id"]),
        secret(),
        now=datetime.now(UTC) - timedelta(minutes=4, seconds=50),
    )
    expired = create_document_token(
        account.user_id,
        uuid.UUID(document["id"]),
        secret(),
        now=datetime.now(UTC) - timedelta(minutes=5, seconds=10),
    )

    ok = await api_client.get(f"{URL}/{document['id']}/content", params={"token": just_valid})
    late = await api_client.get(f"{URL}/{document['id']}/content", params={"token": expired})

    assert ok.status_code == 200
    assert late.status_code == 401
    assert late.json()["error"]["code"] == "AUTH_EXPIRED"


async def test_a_token_is_for_one_document_only(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    first = await upload(api_client, account, JPEG)
    second = await upload(api_client, account, PNG)
    token = (
        await api_client.post(f"{URL}/{first['id']}/access-token", headers=account.headers)
    ).json()["token"]

    other = await api_client.get(f"{URL}/{second['id']}/content", params={"token": token})

    assert other.status_code == 401
    assert other.json()["error"]["code"] == "AUTH_INVALID_TOKEN"
    assert PNG not in other.content


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "x" * 3000])
async def test_bad_or_missing_tokens_are_refused(token: str, api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)

    response = await api_client.get(f"{URL}/{document['id']}/content", params={"token": token})

    assert response.status_code in (401, 422)
    assert JPEG not in response.content


async def test_no_token_at_all_is_422(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)

    assert (await api_client.get(f"{URL}/{document['id']}/content")).status_code == 422


async def test_an_access_token_is_not_a_document_token_and_the_other_way_round(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)
    as_document_token = create_access_token(account.user_id, secret())
    document_token = create_document_token(account.user_id, uuid.UUID(document["id"]), secret())

    wrong_way = await api_client.get(
        f"{URL}/{document['id']}/content", params={"token": as_document_token}
    )
    other_way = await api_client.get("/api/v1/me", headers=bearer(document_token))

    assert wrong_way.status_code == 401
    assert other_way.status_code == 401


async def test_a_token_signed_with_another_secret_is_refused(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)
    forged = create_document_token(
        account.user_id, uuid.UUID(document["id"]), "another-secret-" * 4
    )

    response = await api_client.get(f"{URL}/{document['id']}/content", params={"token": forged})

    assert response.status_code == 401


async def test_a_token_for_a_deleted_document_gives_404(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)
    token = (
        await api_client.post(f"{URL}/{document['id']}/access-token", headers=account.headers)
    ).json()["token"]
    await api_client.delete(f"{URL}/{document['id']}", headers=account.headers)

    response = await api_client.get(f"{URL}/{document['id']}/content", params={"token": token})

    assert response.status_code == 404


async def test_the_token_never_appears_in_the_logs(
    api_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)
    token = (
        await api_client.post(f"{URL}/{document['id']}/access-token", headers=account.headers)
    ).json()["token"]

    with caplog.at_level(logging.DEBUG):
        await api_client.get(f"{URL}/{document['id']}/content", params={"token": token})

    # Only the app's own loggers: the test client (httpx) logs the URL it requested itself.
    app_records = [r for r in caplog.records if r.name.startswith("receiptbox")]
    assert app_records
    assert token not in " ".join(f"{r.getMessage()} {r.__dict__}" for r in app_records)


# ---- metadata and delete ---------------------------------------------------------------------


async def test_metadata_and_delete(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    account = await new_account(api_client)
    document = await upload(api_client, account)

    meta = await api_client.get(f"{URL}/{document['id']}", headers=account.headers)
    deleted = await api_client.delete(f"{URL}/{document['id']}", headers=account.headers)
    again = await api_client.delete(f"{URL}/{document['id']}", headers=account.headers)

    assert meta.json()["id"] == document["id"]
    assert deleted.status_code == 204
    assert again.status_code == 404
    assert await fetch_all(api_app, "SELECT id FROM documents") == []
    assert stored_files(storage_root) == []


async def test_every_endpoint_needs_a_login_except_content(api_client: AsyncClient) -> None:
    some = uuid.uuid4()

    assert (await api_client.post(URL, files=upload_files(JPEG))).status_code == 401
    assert (await api_client.get(f"{URL}/{some}")).status_code == 401
    assert (await api_client.post(f"{URL}/{some}/access-token")).status_code == 401
    assert (await api_client.delete(f"{URL}/{some}")).status_code == 401


# ---- isolation between users -----------------------------------------------------------------


async def test_user_b_cannot_see_use_or_delete_user_as_document(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    document = await upload(api_client, owner)
    doc_id = document["id"]

    assert (await api_client.get(f"{URL}/{doc_id}", headers=other.headers)).status_code == 404
    token = await api_client.post(f"{URL}/{doc_id}/access-token", headers=other.headers)
    assert token.status_code == 404
    assert (await api_client.delete(f"{URL}/{doc_id}", headers=other.headers)).status_code == 404

    # Still there for the owner, file untouched.
    assert (await api_client.get(f"{URL}/{doc_id}", headers=owner.headers)).status_code == 200
    assert len(stored_files(storage_root)) == 1


async def test_a_token_names_its_user_user_b_cannot_make_one_for_user_as_document(
    api_client: AsyncClient,
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    document = await upload(api_client, owner)
    # A token B signs for A's document id carries B's user id: A's file is not found for B.
    forged = create_document_token(other.user_id, uuid.UUID(document["id"]), secret())

    response = await api_client.get(f"{URL}/{document['id']}/content", params={"token": forged})

    assert response.status_code == 404


async def test_deleting_the_account_removes_documents_and_files(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    account = await new_account(api_client)
    await upload(api_client, account)
    await upload(api_client, account, PDF)
    assert len(stored_files(storage_root)) == 2

    assert (await api_client.delete("/api/v1/me", headers=account.headers)).status_code == 204

    assert await fetch_all(api_app, "SELECT id FROM documents") == []
    assert stored_files(storage_root) == []


# ---- the storage layer on its own ------------------------------------------------------------


def test_local_storage_round_trip_and_keys(storage_root: Path) -> None:
    storage = LocalStorage(storage_root)
    user_id = uuid.uuid4()

    key = storage.new_key(user_id)
    storage.save(key, b"hello")

    assert key.startswith(f"users/{user_id}/") and len(key.split("/")[-1]) == 32
    assert storage.read(key) == b"hello"
    storage.delete(key)
    storage.delete(key)  # deleting twice is fine
    with pytest.raises(StorageError):
        storage.read(key)


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "users/../../x/" + "a" * 32,
        "users/not-a-uuid/" + "a" * 32,
        f"users/{uuid.uuid4()}/../../" + "a" * 32,
        f"users/{uuid.uuid4()}/" + "A" * 32,
        f"users/{uuid.uuid4()}/short",
        "/absolute/path",
        "",
    ],
)
def test_local_storage_refuses_keys_that_could_escape(key: str, storage_root: Path) -> None:
    storage = LocalStorage(storage_root)

    with pytest.raises(StorageError):
        storage.save(key, b"x")
    with pytest.raises(StorageError):
        storage.read(key)
    with pytest.raises(StorageError):
        storage.delete(key)


def test_the_app_uses_the_configured_storage_root(storage_root: Path) -> None:
    from app.main import create_app

    app = create_app(make_test_settings(storage_root=str(storage_root)))

    assert isinstance(app.state.storage, LocalStorage)
