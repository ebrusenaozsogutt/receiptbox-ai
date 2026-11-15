"""P00 tests: health endpoint (needs the test database up), error shape, log privacy."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import NotFoundError
from app.core.logging import JsonFormatter
from app.main import create_app
from tests.conftest import make_test_settings


async def test_health_ok_when_db_is_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


async def test_health_reports_db_error_when_db_is_down() -> None:
    # Port 1 is closed, so the connection is refused immediately.
    broken_app = create_app(
        make_test_settings(database_url="postgresql+asyncpg://x:x@127.0.0.1:1/x")
    )
    transport = ASGITransport(app=broken_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    await broken_app.state.engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "error"}


async def test_unknown_route_uses_error_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert isinstance(body["error"]["message"], str)


async def test_domain_error_is_mapped_to_error_shape(app: FastAPI) -> None:
    @app.get("/test/domain-error")
    async def raise_domain_error() -> None:
        raise NotFoundError("Receipt not found.")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/domain-error")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Receipt not found."}}


async def test_unexpected_error_does_not_leak_details(app: FastAPI) -> None:
    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError("secret-detail-4242")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-detail-4242" not in response.text


async def test_validation_error_does_not_echo_input(app: FastAPI) -> None:
    class Payload(BaseModel):
        amount_minor: int

    @app.post("/test/validate")
    async def validate(payload: Payload) -> dict[str, int]:
        return {"amount_minor": payload.amount_minor}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/test/validate", json={"amount_minor": "PII-ECHO-TEST"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "PII-ECHO-TEST" not in response.text


async def test_logs_never_contain_body_or_query_string(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    @app.post("/test/echo")
    async def echo() -> dict[str, str]:
        return {"ok": "yes"}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    with caplog.at_level(logging.INFO, logger="receiptbox"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/test/echo?token=QUERY-SECRET",
                content=b"BODY-SECRET",
                headers={"Authorization": "Bearer HEADER-SECRET"},
            )

    formatter = JsonFormatter()
    lines = [formatter.format(record) for record in caplog.records]
    assert any('"path": "/test/echo"' in line for line in lines)  # the request was logged
    for secret in ("BODY-SECRET", "QUERY-SECRET", "HEADER-SECRET"):
        assert all(secret not in line for line in lines)
