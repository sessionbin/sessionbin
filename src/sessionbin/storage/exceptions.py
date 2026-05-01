class StorageError(Exception):
    """Non-application storage failure (disk full, permission denied, etc)."""


class NotFoundError(StorageError):
    """Read targeted a slug that doesn't exist in storage."""
