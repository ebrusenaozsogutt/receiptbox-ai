"""Base repository for user-owned tables.

Hard rule (CLAUDE.md): every repository function that touches user data takes `user_id` and
filters by it. This class makes that the only way to read or write such a table:

- `user_id` is a required positional parameter of every method (omitting it is a TypeError), and it
  must be a `uuid.UUID` (passing None or a str is a TypeError too, so a bug cannot silently turn
  into "no filter" or "filter on NULL").
- The `user_id` filter is added here, in one place, to every query.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.base import Base

DEFAULT_LIST_LIMIT = 100


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


class UserScopedRepository[T: Base]:
    """get / list / count / add / delete for a model that has `id` and `user_id` columns."""

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        if not (hasattr(model, "id") and hasattr(model, "user_id")):
            raise TypeError(f"{model.__name__} is not a user-owned model with id and user_id")
        self._session = session
        self._model = model

    async def get(self, user_id: uuid.UUID, id: uuid.UUID) -> T | None:  # noqa: A002
        """The row, or None if it does not exist *or belongs to another user*."""
        _check_user_id(user_id)
        statement = select(self._model).where(
            self._model.id == id,  # type: ignore[attr-defined]
            self._model.user_id == user_id,  # type: ignore[attr-defined]
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def require(self, user_id: uuid.UUID, id: uuid.UUID) -> T:  # noqa: A002
        """Like get(), but raises NotFoundError (HTTP 404). Another user's row looks missing."""
        row = await self.get(user_id, id)
        if row is None:
            raise NotFoundError()
        return row

    async def list(
        self,
        user_id: uuid.UUID,
        *,
        where: Sequence[ColumnElement[bool]] = (),
        order_by: Sequence[Any] = (),
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> Sequence[T]:
        _check_user_id(user_id)
        statement = (
            select(self._model)
            .where(self._model.user_id == user_id, *where)  # type: ignore[attr-defined]
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def count(self, user_id: uuid.UUID, *, where: Sequence[ColumnElement[bool]] = ()) -> int:
        _check_user_id(user_id)
        statement = (
            select(func.count())
            .select_from(self._model)
            .where(self._model.user_id == user_id, *where)  # type: ignore[attr-defined]
        )
        return (await self._session.execute(statement)).scalar_one()

    async def add(self, user_id: uuid.UUID, **values: Any) -> T:
        """Create a row owned by `user_id`. The owner can only be given as the first argument."""
        _check_user_id(user_id)
        if "user_id" in values:
            raise TypeError("pass user_id as the first argument, not as a value")
        row = self._model(user_id=user_id, **values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, user_id: uuid.UUID, id: uuid.UUID) -> bool:  # noqa: A002
        """Delete one row. Returns False (and deletes nothing) if it is not this user's."""
        _check_user_id(user_id)
        statement = delete(self._model).where(
            self._model.id == id,  # type: ignore[attr-defined]
            self._model.user_id == user_id,  # type: ignore[attr-defined]
        )
        result = await self._session.execute(statement)
        return result.rowcount > 0  # type: ignore[attr-defined]
