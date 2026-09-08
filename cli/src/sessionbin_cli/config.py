from __future__ import annotations

import os
from pathlib import Path

import click
import platformdirs

DEFAULT_SERVER_URL = "https://sessionbin.dev"


def config_dir() -> Path:
    return platformdirs.user_config_path("sessionbin")


def config_file() -> Path:
    return config_dir() / "config.toml"


def _read_config_url() -> str | None:
    path = config_file()
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("server_url"):
            _, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    return None


def _prompt_and_save() -> str:
    click.echo("No server configured. Enter your sessionbin instance URL.")
    url = click.prompt("Server URL", default=DEFAULT_SERVER_URL)
    url = url.rstrip("/")
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'server_url = "{url}"\n')
    click.echo(f"Saved to {path}")
    return url


def resolve_server_url(server_flag: str | None = None) -> str:
    if server_flag:
        return server_flag.rstrip("/")

    env = os.environ.get("SESSIONBIN_URL")
    if env:
        return env.rstrip("/")

    from_config = _read_config_url()
    if from_config:
        return from_config.rstrip("/")

    return _prompt_and_save()
