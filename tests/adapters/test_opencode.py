import json
from collections import Counter

import pytest

from sessionbin.adapters.opencode import _parse_millis, _parse_parts, parse


def _export(*, info_overrides=None, messages=None):
    info = {
        "id": "ses_test",
        "title": "Test session",
        "directory": "/home/alice/project",
        "version": "1.15.0",
        "agent": "build",
        "model": {"id": "claude-sonnet-4-6", "providerID": "test"},
        "time": {"created": 1700000000000, "updated": 1700000060000},
    }
    if info_overrides:
        info.update(info_overrides)
    doc = {"info": info, "messages": messages or []}
    return json.dumps(doc).encode()


def _user_msg(text="hello", msg_id="msg_u1"):
    return {
        "info": {
            "id": msg_id,
            "sessionID": "ses_test",
            "role": "user",
            "time": {"created": 1700000000000},
        },
        "parts": [{"type": "text", "text": text, "id": "prt_1"}],
    }


def _assistant_msg(parts, parent_id="msg_u1", msg_id="msg_a1"):
    return {
        "info": {
            "id": msg_id,
            "sessionID": "ses_test",
            "role": "assistant",
            "parentID": parent_id,
            "time": {"created": 1700000001000, "completed": 1700000002000},
            "modelID": "claude-sonnet-4-6",
            "providerID": "test",
            "finish": "stop",
        },
        "parts": parts,
    }


class TestParse:
    def test_minimal_session(self):
        raw = _export(messages=[_user_msg(), _assistant_msg([{"type": "text", "text": "hi"}])])
        session = parse(raw)
        assert session.harness == "opencode"
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].index == 0
        assert session.turns[1].role == "assistant"
        assert session.turns[1].index == 1

    def test_metadata(self):
        raw = _export(
            info_overrides={"model": {"id": "claude-opus-4"}, "directory": "/work"},
            messages=[_user_msg()],
        )
        session = parse(raw)
        assert session.model == "claude-opus-4"
        assert session.cwd == "/work"

    def test_empty_messages(self):
        raw = _export(messages=[])
        session = parse(raw)
        assert len(session.turns) == 0
        assert session.started_at is None

    def test_timestamp_from_millis(self):
        raw = _export(messages=[_user_msg()])
        session = parse(raw)
        ts = session.turns[0].timestamp
        assert ts is not None
        assert ts.year == 2023
        assert ts.tzinfo is not None


class TestTurnGrouping:
    def test_assistant_messages_merged_by_parent(self):
        msgs = [
            _user_msg(msg_id="msg_u1"),
            _assistant_msg(
                [{"type": "text", "text": "first"}],
                parent_id="msg_u1",
                msg_id="msg_a1",
            ),
            _assistant_msg(
                [{"type": "text", "text": "second"}],
                parent_id="msg_u1",
                msg_id="msg_a2",
            ),
        ]
        session = parse(_export(messages=msgs))
        assert len(session.turns) == 2
        assert session.turns[1].role == "assistant"
        texts = [b.text for b in session.turns[1].blocks if b.kind == "text"]
        assert texts == ["first", "second"]

    def test_separate_user_turns(self):
        msgs = [
            _user_msg("q1", msg_id="msg_u1"),
            _assistant_msg([{"type": "text", "text": "a1"}], parent_id="msg_u1"),
            _user_msg("q2", msg_id="msg_u2"),
            _assistant_msg(
                [{"type": "text", "text": "a2"}],
                parent_id="msg_u2",
                msg_id="msg_a2",
            ),
        ]
        session = parse(_export(messages=msgs))
        assert len(session.turns) == 4
        assert [t.role for t in session.turns] == ["user", "assistant", "user", "assistant"]


class TestPartMapping:
    def test_text(self):
        blocks = _parse_parts([{"type": "text", "text": "hello"}])
        assert len(blocks) == 1
        assert blocks[0].kind == "text"
        assert blocks[0].text == "hello"

    def test_empty_text_skipped(self):
        blocks = _parse_parts([{"type": "text", "text": ""}])
        assert blocks == []

    def test_reasoning_to_thinking(self):
        blocks = _parse_parts(
            [{"type": "reasoning", "text": "hmm", "time": {"start": 1, "end": 2}}]
        )
        assert blocks[0].kind == "thinking"
        assert blocks[0].text == "hmm"

    def test_structural_parts_skipped(self):
        parts = [
            {"type": "step-start"},
            {"type": "step-finish", "reason": "stop", "tokens": {}, "cost": 0},
            {"type": "patch", "hash": "abc", "files": []},
            {"type": "snapshot", "snapshot": "abc"},
        ]
        blocks = _parse_parts(parts)
        assert blocks == []

    def test_unknown_part_warns(self, caplog):
        blocks = _parse_parts([{"type": "mystery"}])
        assert blocks == []
        assert "unknown part type" in caplog.text


class TestToolParts:
    def test_completed_tool_produces_use_and_result(self):
        parts = [
            {
                "type": "tool",
                "tool": "bash",
                "callID": "call_1",
                "state": {
                    "status": "completed",
                    "input": {"command": "ls"},
                    "output": "file.txt\n",
                    "title": "List files",
                    "time": {"start": 1, "end": 2},
                },
            }
        ]
        blocks = _parse_parts(parts)
        assert len(blocks) == 2
        assert blocks[0].kind == "tool_use"
        assert blocks[0].tool_name == "bash"
        assert blocks[0].tool_input == {"command": "ls"}
        assert blocks[0].tool_use_id == "call_1"
        assert blocks[1].kind == "tool_result"
        assert blocks[1].tool_output == "file.txt\n"
        assert blocks[1].tool_use_id == "call_1"
        assert blocks[1].is_error is False

    def test_error_tool_sets_is_error(self):
        parts = [
            {
                "type": "tool",
                "tool": "bash",
                "callID": "call_2",
                "state": {
                    "status": "error",
                    "input": {"command": "bad"},
                    "error": "command not found",
                    "time": {"start": 1, "end": 2},
                },
            }
        ]
        blocks = _parse_parts(parts)
        assert len(blocks) == 2
        assert blocks[1].kind == "tool_result"
        assert blocks[1].is_error is True
        assert blocks[1].tool_output == "command not found"

    def test_pending_tool_no_result(self):
        parts = [
            {
                "type": "tool",
                "tool": "bash",
                "callID": "call_3",
                "state": {"status": "pending", "input": {"command": "ls"}, "raw": ""},
            }
        ]
        blocks = _parse_parts(parts)
        assert len(blocks) == 1
        assert blocks[0].kind == "tool_use"


class TestErrorMessages:
    def test_error_assistant_skipped(self):
        error_msg = {
            "info": {
                "id": "msg_err",
                "sessionID": "ses_test",
                "role": "assistant",
                "parentID": "msg_u1",
                "time": {"created": 1700000001000, "completed": 1700000002000},
                "error": {"name": "APIError", "data": {"message": "403 Forbidden"}},
            },
            "parts": [],
        }
        msgs = [_user_msg(), error_msg]
        session = parse(_export(messages=msgs))
        assert len(session.turns) == 1
        assert session.turns[0].role == "user"


class TestParseMillis:
    def test_valid(self):
        dt = _parse_millis(1700000000000)
        assert dt is not None
        assert dt.year == 2023
        assert dt.tzinfo is not None

    def test_none(self):
        assert _parse_millis(None) is None


class TestFixtureSmoke:
    @pytest.fixture(
        params=[
            "two_plus_two.json",
            "basic_addition.json",
            "git_origin_change.json",
            "agents_md_symlink.json",
        ]
    )
    def session(self, request, opencode_fixtures_dir):
        fixture = opencode_fixtures_dir / request.param
        return parse(fixture.read_bytes())

    def test_has_turns(self, session):
        assert len(session.turns) > 0

    def test_harness(self, session):
        assert session.harness == "opencode"

    def test_metadata_populated(self, session):
        assert session.cwd is not None
        assert session.model is not None
        assert session.started_at is not None
        assert session.ended_at is not None

    def test_user_and_assistant_turns(self, session):
        roles = {t.role for t in session.turns}
        assert "user" in roles
        assert "assistant" in roles

    def test_block_types_present(self, session):
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["text"] > 0
