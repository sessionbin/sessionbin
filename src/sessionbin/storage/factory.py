import functools
from pathlib import Path
from typing import Any

from django.conf import settings

from .base import Storage
from .filesystem import FilesystemStorage

_SUPPORTED_BACKENDS = {"filesystem"}


@functools.lru_cache(maxsize=1)
def get_storage() -> Storage:
    config: dict[str, Any] = settings.SESSIONBIN
    backend: str = config["STORAGE_BACKEND"]
    if backend not in _SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unknown storage backend: {backend!r}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_BACKENDS))}"
        )
    return FilesystemStorage(Path(config["DATA_DIR"]))
