"""Small helpers shared by the auth tests."""

import uuid
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import text

PASSWORD = "Correct-horse-9"


def new_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.test"


async def register(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = PASSWORD,
    is_adult_confirmed: bool = True,
) -> Response:
    return await client.post(
        "/api/v1/auth/register",
        json={
            "email": email if email is not None else new_email(),
            "password": password,
            "is_adult_confirmed": is_adult_confirmed,
        },
    )


async def register_ok(client: AsyncClient, *, email: str | None = None) -> dict[str, Any]:
    """Register and return the token response plus the e-mail that was used."""
    email = email or new_email()
    response = await register(client, email=email)
    assert response.status_code == 201, response.text
    return {**response.json(), "email": email}


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def refresh(client: AsyncClient, refresh_token: str) -> Response:
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def fetch_all(app: FastAPI, sql: str, **params: Any) -> list[tuple]:
    """Run a read-only query on the app's database (to inspect what was stored)."""
    async with app.state.session_factory() as session:
        return [tuple(row) for row in await session.execute(text(sql), params)]
