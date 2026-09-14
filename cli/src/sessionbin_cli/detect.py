from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import platformdirs

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
OPENCODE_DB_PATH = platformdirs.user_data_path("opencode") / "opencode.db"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


@dataclass
class SessionInfo:
    path: Path
    mtime: float
    project: str
    title: str | None
    summary: str | None
    harness: Literal["claude-code", "codex", "opencode"]
    session_id: str | None = None
    worktree: Path | None = None


def _claude_extract_first_user_message(obj: dict) -> str | None:
    if obj.get("type") != "user":
        return None
    msg = obj.get("message", "")
    if isinstance(msg, str):
        text = msg
    elif isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block["text"]
                    break
            else:
                return None
        else:
            return None
    else:
        return None
    text = text.strip()
    if text.startswith("<"):
        return None
    return text if text else None


def _claude_read_metadata(path: Path) -> tuple[str | None, str | None, str | None]:
    title = None
    summary = None
    cwd = None
    try:
        with open(path) as f:
            for line in f:
                obj = json.loads(line)
                if obj.get("type") == "custom-title":
                    title = obj.get("customTitle")
                if summary is None:
                    summary = _claude_extract_first_user_message(obj)
                if cwd is None and "cwd" in obj:
                    cwd = obj["cwd"]
                if title is not None and summary is not None and cwd is not None:
                    break
    except (json.JSONDecodeError, OSError):
        pass
    return title, summary, cwd


def find_claude_sessions() -> list[SessionInfo]:
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return []
    results: list[SessionInfo] = []
    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            if f.suffix == ".jsonl" and f.is_file():
                title, summary, cwd = _claude_read_metadata(f)
                project = Path(cwd).name if cwd else project_dir.name
                results.append(
                    SessionInfo(
                        path=f,
                        mtime=f.stat().st_mtime,
                        project=project,
                        title=title,
                        summary=summary,
                        harness="claude-code",
                        session_id=f.stem,
                    )
                )
    results.sort(key=lambda x: x.mtime, reverse=True)
    return results


def find_opencode_sessions() -> list[SessionInfo]:
    if not OPENCODE_DB_PATH.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{OPENCODE_DB_PATH}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return []
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.directory, s.time_updated, p.worktree "
            "FROM session s "
            "JOIN project p ON s.project_id = p.id "
            "WHERE s.time_archived IS NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    results: list[SessionInfo] = []
    for sid, title, directory, time_updated, worktree in rows:
        project = Path(directory).name if directory else Path(worktree).name
        results.append(
            SessionInfo(
                path=Path(directory or worktree),
                mtime=time_updated / 1000,
                project=project,
                title=title,
                summary=None,
                session_id=sid,
                worktree=Path(worktree),
                harness="opencode",
            )
        )
    return results


def codex_read_metadata(path: Path) -> tuple[str | None, str | None, str | None] | None:
    """Return (session id, cwd, first prompt) for a rollout, or None for a sub-agent rollout.

    Sub-agent rollouts (guardian reviews, spawned agents) sit in the same tree with a
    non-user thread_source; they are pieces of another session, so they are not listed.
    """
    session_id = None
    cwd = None
    summary = None
    try:
        with open(path) as f:
            for line in f:
                obj = json.loads(line)
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if obj.get("type") == "session_meta":
                    if payload.get("thread_source") not in (None, "user"):
                        return None
                    session_id = payload.get("id")
                    cwd = payload.get("cwd")
                elif obj.get("type") == "response_item" and payload.get("role") == "user":
                    for part in payload.get("content", []):
                        text = (part.get("text") or "").strip() if isinstance(part, dict) else ""
                        if text and not text.startswith(("<", "# AGENTS.md")):
                            summary = text
                            break
                if summary is not None:
                    break
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        pass
    return session_id, cwd, summary


def find_codex_sessions() -> list[SessionInfo]:
    if not CODEX_SESSIONS_DIR.is_dir():
        return []
    results: list[SessionInfo] = []
    for f in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
        if not f.is_file():
            continue
        metadata = codex_read_metadata(f)
        if metadata is None:
            continue
        session_id, cwd, summary = metadata
        results.append(
            SessionInfo(
                path=f,
                mtime=f.stat().st_mtime,
                project=Path(cwd).name if cwd else "-",
                title=None,
                summary=summary,
                harness="codex",
                session_id=session_id,
            )
        )
    results.sort(key=lambda x: x.mtime, reverse=True)
    return results


Detector = Callable[[], list[SessionInfo]]
DETECTORS: list[Detector] = [find_claude_sessions, find_opencode_sessions, find_codex_sessions]


def find_all_sessions() -> list[SessionInfo]:
    results: list[SessionInfo] = []
    for detector in DETECTORS:
        results.extend(detector())
    results.sort(key=lambda x: x.mtime, reverse=True)
    return results


def most_recent() -> SessionInfo | None:
    results: list[SessionInfo] = []
    for detector in DETECTORS:
        results.extend(detector())
    return max(results, key=lambda s: s.mtime, default=None)
