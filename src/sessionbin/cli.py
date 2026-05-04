from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import questionary

from sessionbin.api import APIError, SessionbinClient
from sessionbin.config import resolve_server_url
from sessionbin.detect import SessionInfo, find_all_sessions, most_recent
from sessionbin.sessions import all as sessions_all
from sessionbin.sessions import get as session_get
from sessionbin.sessions import remove as session_remove
from sessionbin.sessions import save as session_save

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
}


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"


def _time_ago(mtime: float) -> str:
    delta = time.time() - mtime
    if delta < 60:
        return "just now"
    if delta < 3600:
        mins = int(delta / 60)
        return f"{mins}m ago"
    if delta < 86400:
        hours = int(delta / 3600)
        return f"{hours}h ago"
    days = int(delta / 86400)
    return f"{days}d ago"


def _short_summary(info: SessionInfo, max_len: int) -> str:
    text = info.title or info.summary or info.path.name
    text = " ".join(text.splitlines())
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def _pick_session() -> Path | None:
    sessions = find_all_sessions()[:10]
    if not sessions:
        return None

    time_w = max(len(_time_ago(s.mtime)) for s in sessions)
    size_w = max(len(_human_size(s.path.stat().st_size)) for s in sessions)
    proj_w = max(len(s.project) for s in sessions)
    summary_max = 60

    def row(s: SessionInfo) -> str:
        ago = _time_ago(s.mtime)
        size = _human_size(s.path.stat().st_size)
        summary = _short_summary(s, summary_max)
        return f"{ago:<{time_w}}  {size:>{size_w}}  {s.project:<{proj_w}}  {summary}"

    header = (
        f"{'TIME':<{time_w}}  {'SIZE':>{size_w}}  {'PROJECT':<{proj_w}}  SESSION NAME / SUMMARY"
    )
    choices: list[questionary.Choice | questionary.Separator] = [
        questionary.Separator(header),
        *[questionary.Choice(title=row(s), value=s.path) for s in sessions],
    ]
    result = questionary.select(
        "Select a session to upload:",
        choices=choices,
    ).unsafe_ask()
    return result


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """CLI for uploading and managing sessionbin transcripts."""


@cli.command()
@click.argument("path", required=False, type=click.Path(exists=True))
@click.option("--server", default=None, help="Override the server URL.")
@click.option("-l", "--latest", is_flag=True, help="Upload the most recent session.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def upload(path: str | None, server: str | None, latest: bool, yes: bool):
    """Upload a session file."""
    file_path: Path
    if path is not None:
        file_path = Path(path)
    elif latest:
        detected = most_recent()
        if detected is None:
            click.secho("No sessions found.", fg="red", err=True)
            sys.exit(1)
        file_path = detected.path
        stat = file_path.stat()
        size = _human_size(stat.st_size)
        ago = _time_ago(detected.mtime)
        click.echo(f"Found: {file_path} ({size}, modified {ago})")
        if not yes:
            if not click.confirm("Upload?", default=False):
                raise SystemExit(0)
    else:
        picked = _pick_session()
        if picked is None:
            click.secho("No sessions found.", fg="red", err=True)
            sys.exit(1)
        file_path = picked

    file_size = file_path.stat().st_size
    if file_size > MAX_UPLOAD_BYTES:
        click.secho(
            f"File is {_human_size(file_size)}, which exceeds the 10 MB upload limit.",
            fg="red",
            err=True,
        )
        sys.exit(1)

    server_url = resolve_server_url(server)
    client = SessionbinClient(server_url)
    try:
        result = client.upload(file_path)
    except APIError as e:
        click.secho(f"Upload failed: {e.message}", fg="red", err=True)
        sys.exit(1)

    slug = result["slug"]
    view_url = result["url"]
    delete_token = result["delete_token"]
    manage_url = f"{view_url}manage/?token={delete_token}"

    session_save(
        slug,
        {
            "delete_token": delete_token,
            "url": view_url,
            "uploaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "server": server_url,
            "filename": file_path.name,
        },
    )

    click.echo("Uploaded.")
    click.secho(f"View:   {view_url}", fg="green")
    click.secho(f"Manage: {manage_url}", fg="green")


@cli.command("list")
def list_cmd():
    """List locally-tracked uploads."""
    entries = sessions_all()
    if not entries:
        click.echo("No uploads tracked locally.")
        return

    click.echo(f"{'URL':<45} {'FILENAME':<30} UPLOADED")
    for e in entries:
        click.echo(f"{e.get('url', ''):<45} {e.get('filename', ''):<30} {e.get('uploaded_at', '')}")


@cli.command()
@click.argument("slug")
@click.option("--server", default=None, help="Override the server URL.")
def delete(slug: str, server: str | None):
    """Delete an uploaded session."""
    entry = session_get(slug)
    if entry is None:
        click.secho(f"No local record for slug '{slug}'.", fg="red", err=True)
        sys.exit(1)

    server_url = server or entry.get("server")
    if not server_url:
        server_url = resolve_server_url(None)

    client = SessionbinClient(server_url)
    try:
        client.delete(slug, entry["delete_token"])
    except APIError as e:
        click.secho(f"Delete failed: {e.message}", fg="red", err=True)
        sys.exit(1)

    session_remove(slug)
    click.echo(f"Deleted {slug}.")
