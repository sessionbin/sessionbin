from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import questionary

from sessionbin_cli import __version__
from sessionbin_cli.api import APIError, SessionbinClient
from sessionbin_cli.config import resolve_server_url
from sessionbin_cli.detect import SessionInfo, find_all_sessions, most_recent
from sessionbin_cli.sessions import all as sessions_all
from sessionbin_cli.sessions import get as session_get
from sessionbin_cli.sessions import remove as session_remove
from sessionbin_cli.sessions import save as session_save

# Mirrors the default server cap; another server answers 413 with its own.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

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


def _session_size(s: SessionInfo) -> str:
    if s.harness == "opencode":
        return "-"
    try:
        return _human_size(s.path.stat().st_size)
    except OSError:
        return "-"


DEFAULT_PICKER_LIMIT = 20


def _pick_session(show_all: bool = False) -> SessionInfo | None:
    all_sessions = find_all_sessions()
    sessions = all_sessions if show_all else all_sessions[:DEFAULT_PICKER_LIMIT]
    if not sessions:
        return None

    sizes = {id(s): _session_size(s) for s in sessions}
    time_w = max(len(_time_ago(s.mtime)) for s in sessions)
    size_w = max(len(v) for v in sizes.values())
    src_w = max(len(s.harness) for s in sessions)
    proj_w = max(len(s.project) for s in sessions)
    summary_max = 60

    def row(s: SessionInfo) -> str:
        ago = _time_ago(s.mtime)
        summary = _short_summary(s, summary_max)
        return (
            f"{ago:<{time_w}}  {sizes[id(s)]:>{size_w}}  {s.harness:<{src_w}}  "
            f"{s.project:<{proj_w}}  {summary}"
        )

    header = (
        f"{'TIME':<{time_w}}  {'SIZE':>{size_w}}  {'SOURCE':<{src_w}}  "
        f"{'PROJECT':<{proj_w}}  SESSION NAME / SUMMARY"
    )
    choices: list[questionary.Choice | questionary.Separator] = [
        questionary.Separator(header),
        *[questionary.Choice(title=row(s), value=s) for s in sessions],
    ]
    result = questionary.select(
        "Select a session to upload:",
        choices=choices,
        style=questionary.Style([("separator", "fg:#00d26a bold")]),
    ).unsafe_ask()
    return result


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, "-V", "--version")
def cli():
    """CLI for uploading and managing sessionbin transcripts."""


@cli.command()
@click.argument("path", required=False, type=click.Path(exists=True))
@click.option("--server", default=None, help="Override the server URL.")
@click.option("-l", "--latest", is_flag=True, help="Upload the most recent session.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option(
    "-a", "--all", "show_all", is_flag=True, help="Show all sessions (default: latest 20)."
)
def upload(path: str | None, server: str | None, latest: bool, yes: bool, show_all: bool):
    """Upload a session file."""
    session: SessionInfo | None = None

    if path is not None:
        upload_data = Path(path).read_bytes()
        upload_filename = Path(path).name
    elif latest:
        session = most_recent()
        if session is None:
            click.secho("No sessions found.", fg="red", err=True)
            sys.exit(1)
        size = _session_size(session)
        ago = _time_ago(session.mtime)
        click.echo(f"Found: {session.path} ({size}, modified {ago})")
        if not yes:
            if not click.confirm("Upload?", default=False):
                raise SystemExit(0)
        if session.harness == "opencode":
            upload_data, upload_filename = _export_opencode_session(session)
        else:
            upload_data, upload_filename = session.path.read_bytes(), session.path.name
    else:
        session = _pick_session(show_all=show_all)
        if session is None:
            click.secho("No sessions found.", fg="red", err=True)
            sys.exit(1)
        if session.harness == "opencode":
            upload_data, upload_filename = _export_opencode_session(session)
        else:
            upload_data, upload_filename = session.path.read_bytes(), session.path.name

    if len(upload_data) > MAX_UPLOAD_BYTES:
        click.secho(
            f"Upload is {_human_size(len(upload_data))}, which exceeds the "
            f"{_human_size(MAX_UPLOAD_BYTES)} upload limit.",
            fg="red",
            err=True,
        )
        sys.exit(1)

    server_url = resolve_server_url(server)
    client = SessionbinClient(server_url)
    harness = session.harness if session else None
    try:
        result = client.upload(upload_data, upload_filename, harness=harness)
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
            "filename": upload_filename,
        },
    )

    click.echo("Uploaded.")
    click.secho(f"View:   {view_url}", fg="green")
    click.secho(f"Manage: {manage_url}", fg="green")


def _export_opencode_session(session: SessionInfo) -> tuple[bytes, str]:
    binary = shutil.which("opencode")
    if binary is None:
        fallback = Path.home() / ".opencode" / "bin" / "opencode"
        if fallback.is_file():
            binary = str(fallback)
    if binary is None:
        click.secho(
            "opencode binary not found. Install it or add it to PATH.",
            fg="red",
            err=True,
        )
        sys.exit(1)
    if not session.session_id:
        click.secho("Session has no ID for export.", fg="red", err=True)
        sys.exit(1)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
    try:
        with open(tmp_fd, "w") as out:
            proc = subprocess.run(
                [binary, "export", session.session_id],
                stdout=out,
                stderr=subprocess.PIPE,
                cwd=session.worktree,
                timeout=30,
            )
        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace").strip()
            click.secho(f"opencode export failed: {stderr}", fg="red", err=True)
            sys.exit(1)
        return Path(tmp_path).read_bytes(), f"{session.session_id}.json"
    except subprocess.TimeoutExpired:
        click.secho("opencode export timed out after 30 seconds.", fg="red", err=True)
        sys.exit(1)
    except OSError as e:
        click.secho(f"opencode export failed: {e}", fg="red", err=True)
        sys.exit(1)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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
