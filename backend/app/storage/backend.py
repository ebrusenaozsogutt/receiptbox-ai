"""Private file storage (spec 15.2): `StorageBackend` and its local-disk implementation.

Files live under STORAGE_ROOT/users/<user_id>/<uuid> and are never served directly: the API
hands them out only through a signed, short-lived token (see app/security/document_tokens.py).
A storage key is `users/<user uuid>/<32 hex characters>`; nothing a client sends ever becomes
part of a path, and every path is checked to stay inside the storage root.
"""

import re
import uuid
from pathlib import Path
from typing import Protocol

_KEY = re.compile(
    r"^users/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{32}$"
)


class StorageError(Exception):
    """A file could not be stored, read or deleted."""


class StorageBackend(Protocol):
    def new_key(self, user_id: uuid.UUID) -> str: ...

    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def new_key(self, user_id: uuid.UUID) -> str:
        return f"users/{user_id}/{uuid.uuid4().hex}"

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise StorageError("invalid storage key")
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise StorageError("path outside the storage root")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as error:
            raise StorageError("could not write the file") from error

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as error:
            raise StorageError("could not read the file") from error

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as error:
            raise StorageError("could not delete the file") from error
