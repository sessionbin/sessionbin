from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from sessionbin_cli.config import config_dir

SESSIONS_FILE = "sessions.json"


def sessions_path() -> Path:
    return config_dir() / SESSIONS_FILE


def load() -> dict[str, dict]:
    path = sessions_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save(slug: str, entry: dict) -> None:
    data = load()
    data[slug] = entry
    write_all(data)


def get(slug: str) -> dict | None:
    return load().get(slug)


def remove(slug: str) -> None:
    data = load()
    data.pop(slug, None)
    write_all(data)


def all() -> list[dict]:
    data = load()
    entries = [{"slug": slug, **v} for slug, v in data.items()]
    entries.sort(key=lambda e: e.get("uploaded_at", ""), reverse=True)
    return entries


def write_all(data: dict) -> None:
    path = sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
