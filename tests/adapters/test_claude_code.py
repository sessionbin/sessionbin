import json
from collections import Counter

import pytest

from sessionbin.adapters.claude_code import (
    _parse_content,
    _parse_timestamp,
    _process_user_text,
    _strip_ansi,
    parse,
)


def _jsonl(*objs: dict) -> bytes:
    return b"\n".join(json.dumps(o).encode() for o in objs)


def _user_line(content="hello", **extra):
    obj = {
        "type": "user",
        "message": {"role": "user", "content": content},
        "timestamp": "2026-05-01T10:00:00.000Z",
        **extra,
    }
    return obj


def _assistant_line(content="hi", **extra):
    obj = {
        "type": "assistant",
        "message": {"role": "assistant", "content": content},
        "timestamp": "2026-05-01T10:00:05.000Z",
        **extra,
    }
    return obj


class TestParse:
    def test_minimal_session(self):
        raw = _jsonl(_user_line(), _assistant_line())
        session = parse(raw)
        assert session.harness == "claude-code"
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].index == 0
        assert session.turns[1].role == "assistant"
        assert session.turns[1].index == 1

    def test_skipped_types_produce_no_turns(self):
        skipped = [
            "system",
            "attachment",
            "file-history-snapshot",
            "last-prompt",
            "permission-mode",
        ]
        lines = [{"type": t} for t in skipped]
        raw = _jsonl(*lines)
        session = parse(raw)
        assert len(session.turns) == 0

    def test_unknown_type_warns(self, caplog):
        raw = _jsonl({"type": "bogus"})
        session = parse(raw)
        assert len(session.turns) == 0
        assert "unknown type" in caplog.text

    def test_metadata_first_occurrence(self):
        line1 = _user_line(cwd="/first", gitBranch="main")
        line2 = _assistant_line(cwd="/second", gitBranch="dev")
        session = parse(_jsonl(line1, line2))
        assert session.cwd == "/first"
        assert session.git_branch == "main"

    def test_model_from_first_assistant(self):
        a1 = _assistant_line()
        a1["message"]["model"] = "claude-opus-4"
        a2 = _assistant_line()
        a2["message"]["model"] = "claude-sonnet-4"
        session = parse(_jsonl(_user_line(), a1, a2))
        assert session.model == "claude-opus-4"

    def test_timestamps_from_first_and_last_turn(self):
        u = _user_line()
        u["timestamp"] = "2026-05-01T09:00:00.000Z"
        a = _assistant_line()
        a["timestamp"] = "2026-05-01T09:05:00.000Z"
        session = parse(_jsonl(u, a))
        assert session.started_at is not None
        assert session.ended_at is not None
        assert session.started_at < session.ended_at

    def test_empty_input(self):
        session = parse(b"")
        assert len(session.turns) == 0
        assert session.started_at is None
        assert session.ended_at is None

    def test_malformed_json_skipped(self, caplog):
        raw = b"not json\n" + json.dumps(_user_line()).encode()
        session = parse(raw)
        assert len(session.turns) == 1
        assert "malformed JSON" in caplog.text


class TestParseTimestamp:
    def test_valid_iso_z(self):
        ts = _parse_timestamp("2026-05-01T10:00:00.000Z")
        assert ts is not None
        assert ts.year == 2026
        assert ts.tzinfo is not None

    def test_none(self):
        assert _parse_timestamp(None) is None

    def test_invalid(self):
        assert _parse_timestamp("not-a-date") is None


class TestParseContent:
    def test_string(self):
        blocks = _parse_content("hello", 1)
        assert len(blocks) == 1
        assert blocks[0].kind == "text"
        assert blocks[0].text == "hello"

    def test_empty_string(self):
        assert _parse_content("", 1) == []

    def test_non_string_non_list(self):
        assert _parse_content(42, 1) == []

    def test_text_block(self):
        blocks = _parse_content([{"type": "text", "text": "hi"}], 1)
        assert blocks[0].kind == "text"
        assert blocks[0].text == "hi"

    def test_thinking_block(self):
        blocks = _parse_content([{"type": "thinking", "thinking": "hmm"}], 1)
        assert blocks[0].kind == "thinking"
        assert blocks[0].text == "hmm"

    def test_tool_use_block(self):
        blocks = _parse_content(
            [{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"}], 1
        )
        b = blocks[0]
        assert b.kind == "tool_use"
        assert b.tool_name == "Bash"
        assert b.tool_input == {"cmd": "ls"}
        assert b.tool_use_id == "t1"

    def test_tool_result_string(self):
        blocks = _parse_content(
            [{"type": "tool_result", "content": "output", "tool_use_id": "t1"}], 1
        )
        b = blocks[0]
        assert b.kind == "tool_result"
        assert b.tool_output == "output"
        assert b.tool_use_id == "t1"
        assert b.is_error is False

    def test_tool_result_array_content(self):
        content = [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]
        blocks = _parse_content(
            [{"type": "tool_result", "content": content, "tool_use_id": "t1"}], 1
        )
        assert blocks[0].tool_output == "line1\nline2"

    def test_tool_result_is_error(self):
        blocks = _parse_content(
            [{"type": "tool_result", "content": "fail", "tool_use_id": "t1", "is_error": True}], 1
        )
        assert blocks[0].is_error is True

    def test_unknown_block_type_warns(self, caplog):
        blocks = _parse_content([{"type": "magic"}], 1)
        assert blocks == []
        assert "unknown block type" in caplog.text


class TestProcessUserText:
    def test_caveat_skipped(self):
        text = (
            "<local-command-caveat>Caveat: The messages below were generated"
            " by the user while running local commands.</local-command-caveat>"
        )
        assert _process_user_text(text) is None

    def test_command_name_extracted(self):
        text = (
            "<command-name>/model</command-name>"
            " <command-message>model</command-message>"
            " <command-args></command-args>"
        )
        assert _process_user_text(text) == "`/model`"

    def test_command_name_with_args(self):
        text = (
            "<command-name>/effort</command-name>"
            " <command-message>effort</command-message>"
            " <command-args>max</command-args>"
        )
        assert _process_user_text(text) == "`/effort`"

    def test_local_command_stdout_stripped(self):
        text = "<local-command-stdout>Set effort level to max</local-command-stdout>"
        assert _process_user_text(text) == "Set effort level to max"

    def test_plain_text_unchanged(self):
        assert _process_user_text("hello world") == "hello world"


class TestStripAnsi:
    def test_strips_bold(self):
        assert _strip_ansi("\x1b[1mOpus 4.6\x1b[22m") == "Opus 4.6"

    def test_strips_color(self):
        assert _strip_ansi("\x1b[32mgreen\x1b[0m") == "green"

    def test_no_ansi_unchanged(self):
        assert _strip_ansi("plain text") == "plain text"

    def test_multiple_sequences(self):
        assert _strip_ansi("\x1b[1m\x1b[31mred bold\x1b[0m") == "red bold"


class TestAnsiStrippingIntegration:
    def test_ansi_stripped_from_string_content(self):
        raw = _jsonl(_user_line(content="\x1b[1mhello\x1b[0m"))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "hello"

    def test_ansi_stripped_from_text_block(self):
        content = [{"type": "text", "text": "\x1b[32mgreen\x1b[0m"}]
        raw = _jsonl(_assistant_line(content=content))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "green"

    def test_ansi_stripped_from_tool_result(self):
        content = [
            {"type": "tool_result", "content": "\x1b[1mbold output\x1b[22m", "tool_use_id": "t1"}
        ]
        raw = _jsonl(_user_line(content=content))
        session = parse(raw)
        assert session.turns[0].blocks[0].tool_output == "bold output"

    def test_ansi_stripped_from_command_stdout(self):
        text = (
            "<local-command-stdout>"
            "Set model to \x1b[1mOpus 4.6 (1M context)\x1b[22m"
            "</local-command-stdout>"
        )
        raw = _jsonl(_user_line(content=text))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "Set model to Opus 4.6 (1M context)"


class TestLocalCommandIntegration:
    def test_caveat_turn_skipped(self):
        caveat = _user_line(
            content="<local-command-caveat>Caveat: DO NOT respond.</local-command-caveat>"
        )
        raw = _jsonl(caveat, _assistant_line())
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].role == "assistant"

    def test_command_name_turn_rendered(self):
        cmd = _user_line(
            content=(
                "<command-name>/model</command-name>"
                " <command-message>model</command-message>"
                " <command-args></command-args>"
            ),
        )
        raw = _jsonl(cmd)
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].blocks[0].text == "`/model`"

    def test_stdout_turn_rendered(self):
        stdout = _user_line(
            content="<local-command-stdout>Set model to Opus 4.6</local-command-stdout>"
        )
        raw = _jsonl(stdout)
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].blocks[0].text == "Set model to Opus 4.6"

    def test_turn_indices_correct_after_skip(self):
        caveat = _user_line(content="<local-command-caveat>Caveat: skip me.</local-command-caveat>")
        cmd = _user_line(
            content=(
                "<command-name>/effort</command-name>"
                " <command-message>effort</command-message>"
                " <command-args></command-args>"
            ),
        )
        stdout = _user_line(
            content="<local-command-stdout>Set effort level to max</local-command-stdout>"
        )
        real = _user_line(content="Do something")
        raw = _jsonl(caveat, cmd, stdout, real, _assistant_line())
        session = parse(raw)
        assert len(session.turns) == 4
        for i, turn in enumerate(session.turns):
            assert turn.index == i


class TestFixtureSmokeSimple:
    @pytest.fixture
    def session(self, fixtures_dir):
        fixture = fixtures_dir / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
        return parse(fixture.read_bytes())

    def test_has_turns(self, session):
        assert len(session.turns) > 0

    def test_has_both_roles(self, session):
        roles = {t.role for t in session.turns}
        assert roles == {"user", "assistant"}

    def test_harness(self, session):
        assert session.harness == "claude-code"

    def test_metadata_populated(self, session):
        assert session.cwd is not None
        assert session.model is not None
        assert session.started_at is not None
        assert session.ended_at is not None

    def test_block_types_present(self, session):
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["text"] > 0
        assert kinds["tool_use"] > 0
        assert kinds["tool_result"] > 0


class TestFixtureSmoke:
    @pytest.fixture
    def session(self, fixtures_dir):
        fixture = fixtures_dir / "f9e8d7c6-b5a4-3210-fedc-ba9876543210.jsonl"
        return parse(fixture.read_bytes())

    def test_has_turns(self, session):
        assert len(session.turns) > 0

    def test_harness(self, session):
        assert session.harness == "claude-code"

    def test_metadata_populated(self, session):
        assert session.cwd is not None
        assert session.model is not None
        assert session.started_at is not None
        assert session.ended_at is not None

    def test_block_types_present(self, session):
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["text"] > 0
        assert kinds["tool_use"] > 0
        assert kinds["tool_result"] > 0
        assert kinds["thinking"] > 0
