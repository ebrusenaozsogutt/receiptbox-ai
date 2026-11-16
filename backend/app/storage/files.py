"""Where a user's files live on disk: STORAGE_ROOT/users/<user_id>/ (spec 15.2).

Only what account deletion needs. The StorageBackend interface for documents comes in P07.
"""

import shutil
import uuid
from pathlib import Path


def user_storage_dir(storage_root: str | Path, user_id: uuid.UUID) -> Path:
    # user_id is a UUID, so it cannot contain path separators or "..".
    return Path(storage_root).resolve() / "users" / str(user_id)


def delete_user_storage(storage_root: str | Path, user_id: uuid.UUID) -> None:
    """Remove the user's whole folder. Does nothing if it does not exist."""
    directory = user_storage_dir(storage_root, user_id)
    if directory.exists():
        shutil.rmtree(directory)
