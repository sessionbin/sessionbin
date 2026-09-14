import json
from collections import Counter

import pytest

from sessionbin.adapters import parse as detect_parse
from sessionbin.adapters.codex import join_text, parse, parse_item
from sessionbin.adapters.common import parse_timestamp, strip_ansi


def _jsonl(*objs: dict) -> bytes:
    return b"\n".join(json.dumps(o).encode() for o in objs)


def _line(line_type: str, payload: dict, timestamp="2026-05-01T10:00:00.000Z") -> dict:
    return {"timestamp": timestamp, "type": line_type, "payload": payload}


def _session_meta(**extra) -> dict:
    return _line("session_meta", {"id": "01a0", "cwd": "/home/alice/projects/demo", **extra})


def _turn_context(model="gpt-5.6-luna") -> dict:
    return _line("turn_context", {"turn_id": "t1", "model": model})


def _user_line(text="hello", timestamp="2026-05-01T10:00:00.000Z") -> dict:
    payload = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}
    return _line("response_item", payload, timestamp)


def _assistant_line(text="hi", timestamp="2026-05-01T10:00:05.000Z") -> dict:
    payload = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
        "phase": "final_answer",
    }
    return _line("response_item", payload, timestamp)


class TestParse:
    def test_minimal_session(self):
        raw = _jsonl(_session_meta(), _user_line(), _assistant_line())
        session = parse(raw)
        assert session.harness == "codex"
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].index == 0
        assert session.turns[1].role == "assistant"
        assert session.turns[1].index == 1

    def test_model_from_first_turn_context(self):
        raw = _jsonl(
            _session_meta(),
            _turn_context("gpt-5.6-luna"),
            _user_line(),
            _turn_context("gpt-5.6-sol"),
            _user_line("again"),
        )
        assert parse(raw).model == "gpt-5.6-luna"

    def test_no_turn_context_leaves_model_unset(self):
        assert parse(_jsonl(_session_meta(), _user_line())).model is None

    def test_bookkeeping_lines_produce_no_turns(self):
        lines = [
            _session_meta(),
            _line("event_msg", {"type": "task_started"}),
            _line("event_msg", {"type": "item_completed", "item": {"type": "UserMessage"}}),
            _line("world_state", {"full": True, "state": {}}),
            _line("compacted", {"message": "", "replacement_history": []}),
            _line("inter_agent_communication_metadata", {"trigger_turn": False}),
        ]
        assert parse(_jsonl(*lines)).turns == []

    def test_unknown_line_type_warns(self, caplog):
        session = parse(_jsonl({"type": "bogus", "payload": {}}))
        assert session.turns == []
        assert "unknown type" in caplog.text

    def test_line_without_payload_warns(self, caplog):
        session = parse(_jsonl({"type": "response_item"}))
        assert session.turns == []
        assert "without a payload" in caplog.text

    def test_malformed_json_skipped(self, caplog):
        raw = b"not json\n" + json.dumps(_user_line()).encode()
        session = parse(raw)
        assert len(session.turns) == 1
        assert "malformed JSON" in caplog.text

    def test_empty_input(self):
        session = parse(b"")
        assert session.turns == []
        assert session.started_at is None

    def test_timestamps_from_first_and_last_turn(self):
        raw = _jsonl(
            _user_line(timestamp="2026-05-01T09:00:00.000Z"),
            _assistant_line(timestamp="2026-05-01T09:05:00.000Z"),
        )
        session = parse(raw)
        assert session.started_at is not None
        assert session.ended_at is not None
        assert (session.ended_at - session.started_at).total_seconds() == 300


class TestAutoDetect:
    def test_rollout_detected_by_session_meta(self):
        session, _ = detect_parse(_jsonl(_session_meta(), _user_line()))
        assert session.harness == "codex"

    def test_leading_whitespace_tolerated(self):
        session, _ = detect_parse(b"\n" + _jsonl(_session_meta(), _user_line()))
        assert session.harness == "codex"

    def test_claude_code_jsonl_not_mistaken(self):
        line = {"type": "user", "message": {"role": "user", "content": "hi"}}
        session, _ = detect_parse(_jsonl(line))
        assert session.harness == "claude-code"


class TestUserMessages:
    @pytest.mark.parametrize(
        "text",
        [
            "# AGENTS.md instructions for /home/alice/projects/demo\n\n<INSTRUCTIONS>...",
            "<environment_context>\n  <cwd>/home/alice</cwd>\n</environment_context>",
            "<turn_aborted>\nThe user interrupted the previous turn.\n</turn_aborted>",
            "<skill>\n<name>sync</name>\n<path>/home/alice/SKILL.md</path>\n</skill>",
        ],
    )
    def test_injected_messages_skipped(self, text):
        assert parse(_jsonl(_user_line(text))).turns == []

    def test_empty_message_skipped(self):
        assert parse(_jsonl(_user_line(""))).turns == []

    def test_multipart_message_joined(self):
        payload = {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": "first"},
                {"type": "input_text", "text": "second"},
            ],
        }
        session = parse(_jsonl(_line("response_item", payload)))
        assert session.turns[0].blocks[0].text == "first\nsecond"

    def test_developer_message_skipped(self):
        payload = {
            "type": "message",
            "role": "developer",
            "content": [
                {"type": "input_text", "text": "<skills_instructions>...</skills_instructions>"}
            ],
        }
        assert parse(_jsonl(_line("response_item", payload))).turns == []

    def test_shell_command_kept(self):
        text = "<user_shell_command>\n<command>\nls\n</command>\n<result>\nExit code: 0\n</result>"
        session = parse(_jsonl(_user_line(text)))
        assert session.turns[0].blocks[0].text == text


class TestAssistantItems:
    def test_text(self):
        parsed = parse_item(_assistant_line("**hi**")["payload"], 1)
        assert parsed is not None
        role, blocks = parsed
        assert role == "assistant"
        assert blocks[0].kind == "text"
        assert blocks[0].text == "**hi**"

    def test_empty_text_skipped(self):
        assert parse_item(_assistant_line("")["payload"], 1) is None

    def test_reasoning_summary_to_thinking(self):
        item = {
            "type": "reasoning",
            "summary": [
                {"type": "summary_text", "text": "Plan the change."},
                {"type": "summary_text", "text": "Then run it."},
            ],
            "encrypted_content": "gAAAA",
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        role, blocks = parsed
        assert role == "assistant"
        assert blocks[0].kind == "thinking"
        assert blocks[0].text == "Plan the change.\nThen run it."

    def test_reasoning_content_to_thinking(self):
        item = {
            "type": "reasoning",
            "summary": [],
            "content": [{"type": "reasoning_text", "text": "raw"}],
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].text == "raw"

    def test_reasoning_summary_and_content_separated(self):
        item = {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "S"}],
            "content": [{"type": "reasoning_text", "text": "C"}],
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].text == "S\nC"

    def test_empty_reasoning_keeps_blank_thinking_block(self):
        parsed = parse_item({"type": "reasoning", "summary": [], "encrypted_content": "x"}, 1)
        assert parsed is not None
        assert parsed[1][0].kind == "thinking"
        assert parsed[1][0].text == ""

    def test_inter_agent_message_skipped(self):
        item = {"type": "agent_message", "author": "/root/a", "recipient": "/root", "content": []}
        assert parse_item(item, 1) is None

    def test_unknown_item_warns(self, caplog):
        assert parse_item({"type": "mystery"}, 7) is None
        assert "unknown item type 'mystery' on line 7" in caplog.text


class TestToolItems:
    def test_function_call_parses_arguments(self):
        item = {
            "type": "function_call",
            "name": "wait",
            "arguments": '{"cell_id": "21", "yield_time_ms": 10000}',
            "call_id": "call_1",
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        role, blocks = parsed
        assert role == "assistant"
        assert blocks[0].kind == "tool_use"
        assert blocks[0].tool_name == "wait"
        assert blocks[0].tool_input == {"cell_id": "21", "yield_time_ms": 10000}
        assert blocks[0].tool_use_id == "call_1"

    def test_function_call_unparseable_arguments_kept_raw(self):
        item = {"type": "function_call", "name": "x", "arguments": "not json", "call_id": "c"}
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].tool_input == {"arguments": "not json"}

    def test_function_call_non_object_arguments_kept_raw(self):
        item = {"type": "function_call", "name": "x", "arguments": "[1, 2]", "call_id": "c"}
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].tool_input == {"arguments": "[1, 2]"}

    def test_custom_tool_call_keeps_input_as_text(self):
        item = {"type": "custom_tool_call", "name": "exec", "input": "text('hi')", "call_id": "c"}
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].kind == "tool_use"
        assert parsed[1][0].tool_name == "exec"
        assert parsed[1][0].tool_input is None
        assert parsed[1][0].tool_input_text == "text('hi')"

    @pytest.mark.parametrize("item_type", ["function_call_output", "custom_tool_call_output"])
    def test_output_list_joined(self, item_type):
        item = {
            "type": item_type,
            "call_id": "c",
            "output": [
                {"type": "input_text", "text": "Script completed\n"},
                {"type": "input_text", "text": "{}"},
            ],
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        role, blocks = parsed
        assert role == "assistant"
        assert blocks[0].kind == "tool_result"
        assert blocks[0].tool_use_id == "c"
        assert blocks[0].tool_output == "Script completed\n\n{}"
        assert blocks[0].is_error is False

    def test_output_string(self):
        item = {"type": "custom_tool_call_output", "call_id": "c", "output": "aborted by user"}
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].tool_output == "aborted by user"

    def test_output_object_kept_as_json(self):
        item = {"type": "function_call_output", "call_id": "c", "output": {"content": "x"}}
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].tool_output == '{"content": "x"}'

    def test_output_ansi_stripped(self):
        item = {
            "type": "custom_tool_call_output",
            "call_id": "c",
            "output": "\x1b]0;demo\x07\x1b[32mok\x1b[0m",
        }
        parsed = parse_item(item, 1)
        assert parsed is not None
        assert parsed[1][0].tool_output == "ok"

    def test_call_and_result_pair_up(self):
        call = _line(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": "x", "call_id": "c1"},
        )
        result = _line(
            "response_item", {"type": "custom_tool_call_output", "call_id": "c1", "output": "y"}
        )
        session = parse(_jsonl(_user_line(), call, result))
        assert [t.role for t in session.turns] == ["user", "assistant"]
        assert [b.kind for b in session.turns[1].blocks] == ["tool_use", "tool_result"]
        assert session.turns[1].blocks[0].tool_use_id == session.turns[1].blocks[1].tool_use_id
        assert session.tool_call_count == 1

    def test_parallel_calls_each_get_their_result(self):
        call_a = _line(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": "a", "call_id": "ca"},
        )
        call_b = _line(
            "response_item",
            {"type": "custom_tool_call", "name": "exec", "input": "b", "call_id": "cb"},
        )
        reasoning = _line("response_item", {"type": "reasoning", "summary": []})
        result_a = _line(
            "response_item", {"type": "custom_tool_call_output", "call_id": "ca", "output": "A"}
        )
        result_b = _line(
            "response_item", {"type": "custom_tool_call_output", "call_id": "cb", "output": "B"}
        )
        session = parse(_jsonl(_user_line(), call_a, call_b, reasoning, result_a, result_b))
        assert [t.role for t in session.turns] == ["user", "assistant", "assistant", "assistant"]
        assert [b.kind for b in session.turns[1].blocks] == ["tool_use", "tool_result"]
        assert [b.kind for b in session.turns[2].blocks] == ["tool_use", "tool_result"]
        assert session.turns[1].blocks[1].tool_output == "A"
        assert session.turns[2].blocks[1].tool_output == "B"

    def test_orphan_result_gets_its_own_turn(self):
        result = _line(
            "response_item", {"type": "custom_tool_call_output", "call_id": "c9", "output": "y"}
        )
        session = parse(_jsonl(_user_line(), _assistant_line(), result))
        assert [t.role for t in session.turns] == ["user", "assistant", "assistant"]
        assert session.turns[2].blocks[0].kind == "tool_result"


class TestHelpers:
    def test_join_text_ignores_non_text_parts(self):
        content = [{"type": "input_text", "text": "a"}, {"type": "input_image"}, "junk"]
        assert join_text(content) == "a"

    def test_join_text_non_list(self):
        assert join_text(None) == ""
        assert join_text("text") == ""

    def test_parse_timestamp(self):
        ts = parse_timestamp("2026-05-01T10:00:00.000Z")
        assert ts is not None
        assert ts.year == 2026
        assert ts.tzinfo is not None
        assert parse_timestamp(None) is None
        assert parse_timestamp("nope") is None

    def test_strip_ansi(self):
        assert strip_ansi("\x1b]0;title\x07plain \x1b[1mbold\x1b[22m") == "plain bold"
        assert strip_ansi("\x1b]0;title\x1b\\x") == "x"


class TestFixtureSmoke:
    @pytest.fixture(
        params=[
            "rollout-2026-09-14T10-20-37-01a0a04a-9368-7ca0-9348-89edf9dd73d5.jsonl",
            "rollout-2026-09-14T10-20-48-01a0a04a-bfb2-7e12-8e42-9bdd2783d9d2.jsonl",
            "rollout-2026-09-02T09-15-57-01a06243-0f8d-73f0-bb95-a335e3c53dd8.jsonl",
        ]
    )
    def session(self, request, codex_fixtures_dir):
        fixture = codex_fixtures_dir / request.param
        return parse(fixture.read_bytes())

    def test_has_turns(self, session):
        assert len(session.turns) > 0

    def test_harness(self, session):
        assert session.harness == "codex"

    def test_metadata_populated(self, session):
        assert session.model is not None
        assert session.started_at is not None
        assert session.ended_at is not None
        assert session.ended_at >= session.started_at

    def test_user_and_assistant_turns(self, session):
        roles = {t.role for t in session.turns}
        assert roles == {"user", "assistant"}

    def test_first_turn_is_the_prompt(self, session):
        first = session.turns[0]
        assert first.role == "user"
        assert first.blocks[0].kind == "text"
        assert not first.blocks[0].text.startswith(("#", "<"))


class TestFixtureDetails:
    def test_all_fixtures_auto_detected(self, codex_fixtures_dir):
        for fixture in codex_fixtures_dir.iterdir():
            detected, _ = detect_parse(fixture.read_bytes())
            assert detected.harness == "codex"

    def test_no_tools(self, codex_fixtures_dir):
        fixture = "rollout-2026-09-14T10-20-37-01a0a04a-9368-7ca0-9348-89edf9dd73d5.jsonl"
        session = parse((codex_fixtures_dir / fixture).read_bytes())
        assert session.model == "gpt-5.6-luna"
        assert [t.role for t in session.turns] == ["user", "assistant"]
        assert session.turns[1].blocks[0].text == "2 + 2 equals 4."

    def test_resumed_session_has_two_prompts_and_tools(self, codex_fixtures_dir):
        fixture = "rollout-2026-09-14T10-20-48-01a0a04a-bfb2-7e12-8e42-9bdd2783d9d2.jsonl"
        session = parse((codex_fixtures_dir / fixture).read_bytes())
        prompts = [t for t in session.turns if t.role == "user" and t.blocks[0].kind == "text"]
        assert len(prompts) == 2
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["tool_use"] == 2
        assert kinds["tool_result"] == 2
        assert kinds["thinking"] > 0
        # The resumed turn ran on a different model; the first one wins.
        assert session.model == "gpt-5.6-luna"

    def test_tui_session_tool_output_has_no_terminal_titles(self, codex_fixtures_dir):
        fixture = "rollout-2026-09-02T09-15-57-01a06243-0f8d-73f0-bb95-a335e3c53dd8.jsonl"
        session = parse((codex_fixtures_dir / fixture).read_bytes())
        outputs = [
            b.tool_output or "" for t in session.turns for b in t.blocks if b.kind == "tool_result"
        ]
        assert outputs
        assert "\x1b" not in outputs[0]
        assert "gh auth status" in (session.turns[0].blocks[0].text or "")
