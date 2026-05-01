import gzip
import os
import re
from pathlib import Path

from .exceptions import NotFoundError, StorageError

_SLUG_RE = re.compile(r"^[a-z0-9]+$")
_SLUG_MAX = 32


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug) or len(slug) > _SLUG_MAX:
        raise ValueError(
            f"Invalid slug: {slug!r}. Must match [a-z0-9]+ and be at most {_SLUG_MAX} characters."
        )


class FilesystemStorage:
    def __init__(self, data_dir: Path) -> None:
        self._raw_dir = data_dir / "raw"
        self._fragment_dir = data_dir / "fragments"
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._fragment_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(str(exc)) from exc

    def write_raw(self, slug: str, data: bytes) -> None:
        _validate_slug(slug)
        self._atomic_write(self._raw_dir / f"{slug}.jsonl.gz", gzip.compress(data))

    def read_raw(self, slug: str) -> bytes:
        _validate_slug(slug)
        path = self._raw_dir / f"{slug}.jsonl.gz"
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise NotFoundError(slug)

    def write_fragment(self, slug: str, html: str) -> None:
        _validate_slug(slug)
        self._atomic_write(self._fragment_dir / f"{slug}.html", html.encode("utf-8"))

    def read_fragment(self, slug: str) -> str:
        _validate_slug(slug)
        path = self._fragment_dir / f"{slug}.html"
        try:
            return path.read_text("utf-8")
        except FileNotFoundError:
            raise NotFoundError(slug)

    def delete(self, slug: str) -> None:
        _validate_slug(slug)
        (self._raw_dir / f"{slug}.jsonl.gz").unlink(missing_ok=True)
        (self._fragment_dir / f"{slug}.html").unlink(missing_ok=True)
