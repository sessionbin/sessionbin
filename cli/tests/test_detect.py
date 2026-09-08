import json
import os
import sqlite3
import time

from sessionbin_cli.detect import find_claude_sessions, find_opencode_sessions, most_recent


def _make_project(tmp_path, name, files):
    projects = tmp_path / ".claude" / "projects"
    project_dir = projects / name
    project_dir.mkdir(parents=True)
    paths = []
    for fname in files:
        p = project_dir / fname
        p.write_text("{}")
        paths.append(p)
    return paths


def test_finds_jsonl_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    _make_project(tmp_path, "-home-user-repos-myproject", ["abc.jsonl", "def.jsonl"])
    results = find_claude_sessions()
    names = [s.path.name for s in results]
    assert "abc.jsonl" in names
    assert "def.jsonl" in names


def test_skips_subagents(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    projects = tmp_path / ".claude" / "projects" / "-home-user-repos-proj"
    projects.mkdir(parents=True)
    (projects / "session.jsonl").write_text("{}")
    subagents = projects / "subagents"
    subagents.mkdir()
    (subagents / "sub.jsonl").write_text("{}")
    results = find_claude_sessions()
    names = [s.path.name for s in results]
    assert "session.jsonl" in names
    assert "sub.jsonl" not in names


def test_sorted_by_mtime_descending(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    paths = _make_project(tmp_path, "-home-user-repos-proj", ["old.jsonl", "new.jsonl"])
    os.utime(paths[0], (time.time() - 100, time.time() - 100))
    os.utime(paths[1], (time.time(), time.time()))
    results = find_claude_sessions()
    assert results[0].path.name == "new.jsonl"
    assert results[1].path.name == "old.jsonl"


def test_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", tmp_path / "nonexistent.db")
    paths = _make_project(tmp_path, "-home-user-repos-proj", ["old.jsonl", "new.jsonl"])
    os.utime(paths[0], (time.time() - 100, time.time() - 100))
    os.utime(paths[1], (time.time(), time.time()))
    result = most_recent()
    assert result is not None
    assert result.path.name == "new.jsonl"


def test_most_recent_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", tmp_path / "nonexistent.db")
    (tmp_path / ".claude" / "projects").mkdir(parents=True)
    assert most_recent() is None


def test_ignores_non_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    _make_project(tmp_path, "-home-user-repos-proj", ["readme.md", "session.jsonl"])
    results = find_claude_sessions()
    names = [s.path.name for s in results]
    assert "session.jsonl" in names
    assert "readme.md" not in names


def test_no_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    assert find_claude_sessions() == []


def test_project_from_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    projects = tmp_path / ".claude" / "projects" / "-home-user-repos-sessionbin-cli"
    projects.mkdir(parents=True)
    lines = [
        json.dumps({"type": "assistant", "cwd": "/home/user/repos/sessionbin-cli"}),
    ]
    (projects / "session.jsonl").write_text("\n".join(lines))
    results = find_claude_sessions()
    assert results[0].project == "sessionbin-cli"


def test_project_falls_back_to_dir_name(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    _make_project(tmp_path, "-home-user-repos-myproject", ["session.jsonl"])
    results = find_claude_sessions()
    assert results[0].project == "-home-user-repos-myproject"


def test_reads_custom_title(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    projects = tmp_path / ".claude" / "projects" / "-home-user-repos-proj"
    projects.mkdir(parents=True)
    lines = [
        json.dumps({"type": "custom-title", "customTitle": "My session"}),
        json.dumps({"type": "user", "message": "do something"}),
    ]
    (projects / "session.jsonl").write_text("\n".join(lines))
    results = find_claude_sessions()
    assert results[0].title == "My session"
    assert results[0].summary == "do something"


def _create_opencode_db(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE project (  id TEXT PRIMARY KEY,  worktree TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE session ("
        "  id TEXT PRIMARY KEY,"
        "  title TEXT,"
        "  directory TEXT,"
        "  time_updated INTEGER,"
        "  time_archived INTEGER,"
        "  project_id TEXT REFERENCES project(id)"
        ")"
    )
    conn.commit()
    return conn


def test_claude_sessions_have_claude_code_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    _make_project(tmp_path, "-home-user-repos-proj", ["session.jsonl"])
    results = find_claude_sessions()
    assert results[0].harness == "claude-code"


def test_opencode_finds_sessions(tmp_path, monkeypatch):
    db_path = tmp_path / "opencode.db"
    conn = _create_opencode_db(db_path)
    conn.execute("INSERT INTO project VALUES ('proj1', '/home/user/repos/myapp')")
    conn.execute(
        "INSERT INTO session VALUES "
        "('ses_abc123', 'Fix login bug', '/home/user/repos/myapp', 1700000000000, NULL, 'proj1')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", db_path)

    results = find_opencode_sessions()

    assert len(results) == 1
    s = results[0]
    assert s.session_id == "ses_abc123"
    assert s.title == "Fix login bug"
    assert s.project == "myapp"
    assert s.mtime == 1700000000.0
    assert s.harness == "opencode"
    assert s.worktree is not None
    assert str(s.worktree) == "/home/user/repos/myapp"


def test_opencode_excludes_archived(tmp_path, monkeypatch):
    db_path = tmp_path / "opencode.db"
    conn = _create_opencode_db(db_path)
    conn.execute("INSERT INTO project VALUES ('proj1', '/home/user/repos/myapp')")
    conn.execute(
        "INSERT INTO session VALUES "
        "('ses_active', 'Active', '/home/user/repos/myapp', 1700000000000, NULL, 'proj1')"
    )
    conn.execute(
        "INSERT INTO session VALUES "
        "('ses_archived', 'Archived', '/home/user/repos/myapp',"
        " 1700000000000, 1700001000000, 'proj1')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", db_path)

    results = find_opencode_sessions()

    assert len(results) == 1
    assert results[0].session_id == "ses_active"


def test_opencode_empty_db(tmp_path, monkeypatch):
    db_path = tmp_path / "opencode.db"
    conn = _create_opencode_db(db_path)
    conn.close()
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", db_path)

    assert find_opencode_sessions() == []


def test_opencode_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", tmp_path / "nonexistent.db")
    assert find_opencode_sessions() == []
