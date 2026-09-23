import json
import os
import sqlite3
import time
from pathlib import Path

from sessionbin_cli.detect import (
    env_dir,
    find_claude_sessions,
    find_codex_sessions,
    find_opencode_sessions,
    find_pi_sessions,
    most_recent,
)


def test_env_dir_uses_env_var(monkeypatch):
    monkeypatch.setenv("SESSIONBIN_TEST_DIR", "/custom/dir")
    assert env_dir("SESSIONBIN_TEST_DIR", Path("/default")) == Path("/custom/dir")


def test_env_dir_expands_tilde(monkeypatch):
    monkeypatch.setenv("SESSIONBIN_TEST_DIR", "~/custom")
    assert env_dir("SESSIONBIN_TEST_DIR", Path("/default")) == Path.home() / "custom"


def test_env_dir_falls_back_when_unset_or_empty(monkeypatch):
    monkeypatch.delenv("SESSIONBIN_TEST_DIR", raising=False)
    assert env_dir("SESSIONBIN_TEST_DIR", Path("/default")) == Path("/default")
    monkeypatch.setenv("SESSIONBIN_TEST_DIR", "")
    assert env_dir("SESSIONBIN_TEST_DIR", Path("/default")) == Path("/default")


def make_project(tmp_path, name, files):
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
    make_project(tmp_path, "-home-user-repos-myproject", ["abc.jsonl", "def.jsonl"])
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
    paths = make_project(tmp_path, "-home-user-repos-proj", ["old.jsonl", "new.jsonl"])
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
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr("sessionbin_cli.detect.PI_SESSIONS_DIR", tmp_path / "nonexistent")
    paths = make_project(tmp_path, "-home-user-repos-proj", ["old.jsonl", "new.jsonl"])
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
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr("sessionbin_cli.detect.PI_SESSIONS_DIR", tmp_path / "nonexistent")
    (tmp_path / ".claude" / "projects").mkdir(parents=True)
    assert most_recent() is None


def test_ignores_non_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sessionbin_cli.detect.CLAUDE_PROJECTS_DIR", tmp_path / ".claude" / "projects"
    )
    make_project(tmp_path, "-home-user-repos-proj", ["readme.md", "session.jsonl"])
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
    make_project(tmp_path, "-home-user-repos-myproject", ["session.jsonl"])
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


def create_opencode_db(db_path):
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
    make_project(tmp_path, "-home-user-repos-proj", ["session.jsonl"])
    results = find_claude_sessions()
    assert results[0].harness == "claude-code"


def test_opencode_finds_sessions(tmp_path, monkeypatch):
    db_path = tmp_path / "opencode.db"
    conn = create_opencode_db(db_path)
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
    conn = create_opencode_db(db_path)
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
    conn = create_opencode_db(db_path)
    conn.close()
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", db_path)

    assert find_opencode_sessions() == []


def test_opencode_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr("sessionbin_cli.detect.OPENCODE_DB_PATH", tmp_path / "nonexistent.db")
    assert find_opencode_sessions() == []


def codex_rollout(path, session_id="01a0", cwd="/home/user/repos/proj", thread_source="user"):
    def user_message(text):
        return {
            "timestamp": "2026-09-14T14:20:38.644Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }

    lines = [
        {
            "timestamp": "2026-09-14T14:20:37.188Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": cwd, "thread_source": thread_source},
        },
        {
            "timestamp": "2026-09-14T14:20:38.644Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "<skills_instructions>..."}],
            },
        },
        user_message("# AGENTS.md instructions for /home/user/repos/proj"),
        user_message("<environment_context>...</environment_context>"),
        user_message("Fix the bug"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


def test_codex_finds_sessions(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".codex" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", sessions_dir)
    old = codex_rollout(sessions_dir / "2026" / "09" / "13" / "rollout-old.jsonl", session_id="old")
    new = codex_rollout(sessions_dir / "2026" / "09" / "14" / "rollout-new.jsonl", session_id="new")
    os.utime(old, (time.time() - 100, time.time() - 100))
    os.utime(new, (time.time(), time.time()))

    results = find_codex_sessions()

    assert [s.session_id for s in results] == ["new", "old"]
    s = results[0]
    assert s.harness == "codex"
    assert s.path == new
    assert s.project == "proj"
    assert s.title is None
    assert s.summary == "Fix the bug"


def test_codex_skips_subagent_rollouts(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".codex" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", sessions_dir)
    codex_rollout(sessions_dir / "2026" / "09" / "14" / "rollout-main.jsonl", session_id="main")
    codex_rollout(
        sessions_dir / "2026" / "09" / "14" / "rollout-sub.jsonl",
        session_id="sub",
        thread_source="guardian_review",
    )

    results = find_codex_sessions()

    assert [s.session_id for s in results] == ["main"]


def test_codex_lists_rollout_without_thread_source(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".codex" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", sessions_dir)
    codex_rollout(sessions_dir / "rollout-old-version.jsonl", session_id="v", thread_source=None)

    assert [s.session_id for s in find_codex_sessions()] == ["v"]


def test_codex_tolerates_malformed_file(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".codex" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", sessions_dir)
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "rollout-broken.jsonl").write_text("not json\n")

    results = find_codex_sessions()

    assert len(results) == 1
    assert results[0].summary is None
    assert results[0].project == "-"


def test_codex_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("sessionbin_cli.detect.CODEX_SESSIONS_DIR", tmp_path / "nonexistent")
    assert find_codex_sessions() == []


def pi_session(
    path, session_id="01a0", cwd="/home/user/repos/proj", name=None, prompt="Fix the bug"
):
    lines = [
        {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": "2026-09-14T17:00:47.986Z",
            "cwd": cwd,
        },
        {
            "type": "model_change",
            "id": "e1",
            "parentId": None,
            "timestamp": "2026-09-14T17:00:48.023Z",
            "provider": "mango",
            "modelId": "qwen38",
        },
        {
            "type": "message",
            "id": "e2",
            "parentId": "e1",
            "timestamp": "2026-09-14T17:00:48.028Z",
            "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
        },
    ]
    if name is not None:
        lines.insert(
            1,
            {
                "type": "session_info",
                "id": "e0",
                "parentId": None,
                "timestamp": "2026-09-14T17:00:47.986Z",
                "name": name,
            },
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


def test_pi_finds_sessions(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".pi" / "agent" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.PI_SESSIONS_DIR", sessions_dir)
    project_dir = sessions_dir / "--home-user-repos-proj--"
    old = pi_session(project_dir / "2026-09-13T10-00-00-000Z_old.jsonl", session_id="old")
    new = pi_session(
        project_dir / "2026-09-14T10-00-00-000Z_new.jsonl", session_id="new", name="arithmetic"
    )
    os.utime(old, (time.time() - 100, time.time() - 100))
    os.utime(new, (time.time(), time.time()))

    results = find_pi_sessions()

    assert [s.session_id for s in results] == ["new", "old"]
    s = results[0]
    assert s.harness == "pi"
    assert s.path == new
    assert s.project == "proj"
    assert s.title == "arithmetic"
    assert s.summary == "Fix the bug"
    assert results[1].title is None


def test_pi_skips_files_without_session_header(tmp_path, monkeypatch):
    sessions_dir = tmp_path / ".pi" / "agent" / "sessions"
    monkeypatch.setattr("sessionbin_cli.detect.PI_SESSIONS_DIR", sessions_dir)
    project_dir = sessions_dir / "--home-user-repos-proj--"
    pi_session(project_dir / "real.jsonl", session_id="real")
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "other.jsonl").write_text(json.dumps({"type": "user", "message": {}}) + "\n")
    (project_dir / "broken.jsonl").write_text("not json\n")

    assert [s.session_id for s in find_pi_sessions()] == ["real"]


def test_pi_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("sessionbin_cli.detect.PI_SESSIONS_DIR", tmp_path / "nonexistent")
    assert find_pi_sessions() == []
