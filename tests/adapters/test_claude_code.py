import json
from collections import Counter

import pytest

from sessionbin.adapters.claude_code import parse, parse_content, process_user_text
from sessionbin.adapters.common import parse_timestamp, strip_ansi


def jsonl(*objs: dict) -> bytes:
    return b"\n".join(json.dumps(o).encode() for o in objs)


def user_line(content="hello", **extra):
    obj = {
        "type": "user",
        "message": {"role": "user", "content": content},
        "timestamp": "2026-05-01T10:00:00.000Z",
        **extra,
    }
    return obj


def assistant_line(content="hi", **extra):
    obj = {
        "type": "assistant",
        "message": {"role": "assistant", "content": content},
        "timestamp": "2026-05-01T10:00:05.000Z",
        **extra,
    }
    return obj


class TestParse:
    def test_minimal_session(self):
        raw = jsonl(user_line(), assistant_line())
        session = parse(raw)
        assert session.harness == "claude-code"
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].index == 0
        assert session.turns[1].role == "assistant"
        assert session.turns[1].index == 1

    def test_skipped_types_produce_no_turns(self, caplog):
        skipped = [
            "system",
            "attachment",
            "file-history-snapshot",
            "last-prompt",
            "permission-mode",
            "atis-latch",
            "cost-state",
        ]
        lines = [{"type": t} for t in skipped]
        raw = jsonl(*lines)
        session = parse(raw)
        assert len(session.turns) == 0
        assert "unknown type" not in caplog.text

    def test_unknown_type_warns(self, caplog):
        raw = jsonl({"type": "bogus"})
        session = parse(raw)
        assert len(session.turns) == 0
        assert "unknown type" in caplog.text

    def test_model_from_first_assistant(self):
        a1 = assistant_line()
        a1["message"]["model"] = "claude-opus-4"
        a2 = assistant_line()
        a2["message"]["model"] = "claude-sonnet-4"
        session = parse(jsonl(user_line(), a1, a2))
        assert session.model == "claude-opus-4"

    def test_timestamps_from_first_and_last_turn(self):
        u = user_line()
        u["timestamp"] = "2026-05-01T09:00:00.000Z"
        a = assistant_line()
        a["timestamp"] = "2026-05-01T09:05:00.000Z"
        session = parse(jsonl(u, a))
        assert session.started_at is not None
        assert session.ended_at is not None
        assert session.started_at < session.ended_at

    def test_empty_input(self):
        session = parse(b"")
        assert len(session.turns) == 0
        assert session.started_at is None
        assert session.ended_at is None

    def test_malformed_json_skipped(self, caplog):
        raw = b"not json\n" + json.dumps(user_line()).encode()
        session = parse(raw)
        assert len(session.turns) == 1
        assert "malformed JSON" in caplog.text


class TestMetaMessages:
    @pytest.mark.parametrize(
        "content",
        [
            [{"type": "text", "text": "[Image: source: /home/alice/.claude/image-cache/x/1.png]"}],
            "Base directory for this skill: /home/alice/.claude/skills/deploy",
            "## Context Usage\n\n**Model:** claude-opus-5",
        ],
    )
    def test_meta_user_lines_skipped(self, content):
        session = parse(jsonl(user_line(content=content, isMeta=True, turnCompanion=True)))
        assert session.turns == []

    def test_non_meta_user_line_with_same_text_kept(self):
        raw = jsonl(user_line(content="Base directory for this skill: /x"))
        assert len(parse(raw).turns) == 1


class TestToolResultMerging:
    def test_result_joins_the_turn_that_made_the_call(self):
        call = assistant_line(
            content=[{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"}]
        )
        result = user_line(content=[{"type": "tool_result", "content": "ok", "tool_use_id": "t1"}])
        session = parse(jsonl(user_line(), call, result, assistant_line()))
        assert [t.role for t in session.turns] == ["user", "assistant", "assistant"]
        assert [b.kind for b in session.turns[1].blocks] == ["tool_use", "tool_result"]
        assert [t.index for t in session.turns] == [0, 1, 2]

    def test_parallel_calls_each_get_their_result(self):
        call_a = assistant_line(
            content=[{"type": "tool_use", "name": "Read", "input": {"f": "a"}, "id": "ta"}]
        )
        call_b = assistant_line(
            content=[{"type": "tool_use", "name": "Read", "input": {"f": "b"}, "id": "tb"}]
        )
        result_a = user_line(content=[{"type": "tool_result", "content": "A", "tool_use_id": "ta"}])
        result_b = user_line(content=[{"type": "tool_result", "content": "B", "tool_use_id": "tb"}])
        session = parse(jsonl(user_line(), call_a, call_b, result_a, result_b))
        assert [t.role for t in session.turns] == ["user", "assistant", "assistant"]
        assert [b.tool_output for b in session.turns[1].blocks if b.kind == "tool_result"] == ["A"]
        assert [b.tool_output for b in session.turns[2].blocks if b.kind == "tool_result"] == ["B"]

    def test_result_without_id_stays_a_user_turn(self):
        call = assistant_line(content=[{"type": "tool_use", "name": "Bash", "input": {}}])
        result = user_line(content=[{"type": "tool_result", "content": "ok"}])
        session = parse(jsonl(call, result))
        assert [t.role for t in session.turns] == ["assistant", "user"]

    def test_result_for_a_different_call_stays_a_user_turn(self):
        call = assistant_line(
            content=[{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"}]
        )
        result = user_line(content=[{"type": "tool_result", "content": "ok", "tool_use_id": "t9"}])
        session = parse(jsonl(call, result))
        assert [t.role for t in session.turns] == ["assistant", "user"]

    def test_result_mixed_with_text_stays_a_user_turn(self):
        call = assistant_line(
            content=[{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"}]
        )
        result = user_line(
            content=[
                {"type": "tool_result", "content": "ok", "tool_use_id": "t1"},
                {"type": "text", "text": "and also do this"},
            ]
        )
        session = parse(jsonl(call, result))
        assert [t.role for t in session.turns] == ["assistant", "user"]


class TestParseTimestamp:
    def test_valid_iso_z(self):
        ts = parse_timestamp("2026-05-01T10:00:00.000Z")
        assert ts is not None
        assert ts.year == 2026
        assert ts.tzinfo is not None

    def test_none(self):
        assert parse_timestamp(None) is None

    def test_invalid(self):
        assert parse_timestamp("not-a-date") is None


class TestParseContent:
    def test_string(self):
        blocks = parse_content("hello", 1)
        assert len(blocks) == 1
        assert blocks[0].kind == "text"
        assert blocks[0].text == "hello"

    def test_empty_string(self):
        assert parse_content("", 1) == []

    def test_non_string_non_list(self):
        assert parse_content(42, 1) == []

    def test_text_block(self):
        blocks = parse_content([{"type": "text", "text": "hi"}], 1)
        assert blocks[0].kind == "text"
        assert blocks[0].text == "hi"

    def test_thinking_block(self):
        blocks = parse_content([{"type": "thinking", "thinking": "hmm"}], 1)
        assert blocks[0].kind == "thinking"
        assert blocks[0].text == "hmm"

    def test_tool_use_block(self):
        blocks = parse_content(
            [{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}, "id": "t1"}], 1
        )
        b = blocks[0]
        assert b.kind == "tool_use"
        assert b.tool_name == "Bash"
        assert b.tool_input == {"cmd": "ls"}
        assert b.tool_use_id == "t1"

    def test_tool_result_string(self):
        blocks = parse_content(
            [{"type": "tool_result", "content": "output", "tool_use_id": "t1"}], 1
        )
        b = blocks[0]
        assert b.kind == "tool_result"
        assert b.tool_output == "output"
        assert b.tool_use_id == "t1"
        assert b.is_error is False

    def test_tool_result_array_content(self):
        content = [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}]
        blocks = parse_content(
            [{"type": "tool_result", "content": content, "tool_use_id": "t1"}], 1
        )
        assert blocks[0].tool_output == "line1\nline2"

    def test_tool_result_is_error(self):
        blocks = parse_content(
            [{"type": "tool_result", "content": "fail", "tool_use_id": "t1", "is_error": True}], 1
        )
        assert blocks[0].is_error is True

    def test_unknown_block_type_warns(self, caplog):
        blocks = parse_content([{"type": "magic"}], 1)
        assert blocks == []
        assert "unknown block type" in caplog.text


class TestProcessUserText:
    def test_caveat_skipped(self):
        text = (
            "<local-command-caveat>Caveat: The messages below were generated"
            " by the user while running local commands.</local-command-caveat>"
        )
        assert process_user_text(text) is None

    def test_command_name_extracted(self):
        text = (
            "<command-name>/model</command-name>"
            " <command-message>model</command-message>"
            " <command-args></command-args>"
        )
        assert process_user_text(text) == "`/model`"

    def test_command_name_with_args(self):
        text = (
            "<command-name>/effort</command-name>"
            " <command-message>effort</command-message>"
            " <command-args>max</command-args>"
        )
        assert process_user_text(text) == "`/effort`"

    def test_local_command_stdout_stripped(self):
        text = "<local-command-stdout>Set effort level to max</local-command-stdout>"
        assert process_user_text(text) == "Set effort level to max"

    def test_plain_text_unchanged(self):
        assert process_user_text("hello world") == "hello world"


class TestStripAnsi:
    def test_strips_bold(self):
        assert strip_ansi("\x1b[1mOpus 4.6\x1b[22m") == "Opus 4.6"

    def test_strips_color(self):
        assert strip_ansi("\x1b[32mgreen\x1b[0m") == "green"

    def test_no_ansi_unchanged(self):
        assert strip_ansi("plain text") == "plain text"

    def test_multiple_sequences(self):
        assert strip_ansi("\x1b[1m\x1b[31mred bold\x1b[0m") == "red bold"

    def test_strips_terminal_title(self):
        assert strip_ansi("\x1b]0;demo\x07output") == "output"


class TestAnsiStrippingIntegration:
    def test_ansi_stripped_from_string_content(self):
        raw = jsonl(user_line(content="\x1b[1mhello\x1b[0m"))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "hello"

    def test_ansi_stripped_from_text_block(self):
        content = [{"type": "text", "text": "\x1b[32mgreen\x1b[0m"}]
        raw = jsonl(assistant_line(content=content))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "green"

    def test_ansi_stripped_from_tool_result(self):
        content = [
            {"type": "tool_result", "content": "\x1b[1mbold output\x1b[22m", "tool_use_id": "t1"}
        ]
        raw = jsonl(user_line(content=content))
        session = parse(raw)
        assert session.turns[0].blocks[0].tool_output == "bold output"

    def test_ansi_stripped_from_command_stdout(self):
        text = (
            "<local-command-stdout>"
            "Set model to \x1b[1mOpus 4.6 (1M context)\x1b[22m"
            "</local-command-stdout>"
        )
        raw = jsonl(user_line(content=text))
        session = parse(raw)
        assert session.turns[0].blocks[0].text == "Set model to Opus 4.6 (1M context)"


class TestLocalCommandIntegration:
    def test_caveat_turn_skipped(self):
        caveat = user_line(
            content="<local-command-caveat>Caveat: DO NOT respond.</local-command-caveat>"
        )
        raw = jsonl(caveat, assistant_line())
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].role == "assistant"

    def test_command_name_turn_rendered(self):
        cmd = user_line(
            content=(
                "<command-name>/model</command-name>"
                " <command-message>model</command-message>"
                " <command-args></command-args>"
            ),
        )
        raw = jsonl(cmd)
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].blocks[0].text == "`/model`"

    def test_stdout_turn_rendered(self):
        stdout = user_line(
            content="<local-command-stdout>Set model to Opus 4.6</local-command-stdout>"
        )
        raw = jsonl(stdout)
        session = parse(raw)
        assert len(session.turns) == 1
        assert session.turns[0].blocks[0].text == "Set model to Opus 4.6"

    def test_turn_indices_correct_after_skip(self):
        caveat = user_line(content="<local-command-caveat>Caveat: skip me.</local-command-caveat>")
        cmd = user_line(
            content=(
                "<command-name>/effort</command-name>"
                " <command-message>effort</command-message>"
                " <command-args></command-args>"
            ),
        )
        stdout = user_line(
            content="<local-command-stdout>Set effort level to max</local-command-stdout>"
        )
        real = user_line(content="Do something")
        raw = jsonl(caveat, cmd, stdout, real, assistant_line())
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
        assert session.model is not None
        assert session.started_at is not None
        assert session.ended_at is not None

    def test_block_types_present(self, session):
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["text"] > 0
        assert kinds["tool_use"] > 0
        assert kinds["tool_result"] > 0
        assert kinds["thinking"] > 0
