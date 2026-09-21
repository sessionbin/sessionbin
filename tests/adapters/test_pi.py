import json
from collections import Counter

import pytest

from sessionbin.adapters import parse as detect_parse
from sessionbin.adapters.pi import format_bash_execution, join_result_text, parse, parse_message


def jsonl(*objs: dict) -> bytes:
    return b"\n".join(json.dumps(o).encode() for o in objs)


def header_line() -> dict:
    return {
        "type": "session",
        "version": 3,
        "id": "01a0",
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/home/alice/projects/demo",
    }


def entry_line(entry_type: str, timestamp="2026-05-01T10:00:00.000Z", **fields) -> dict:
    return {"type": entry_type, "id": "e1", "parentId": None, "timestamp": timestamp, **fields}


def model_change(model_id="qwen38") -> dict:
    return entry_line("model_change", provider="mango", modelId=model_id)


def message_line(message: dict, timestamp="2026-05-01T10:00:00.000Z") -> dict:
    return entry_line("message", timestamp=timestamp, message=message)


def user_line(text="hello", timestamp="2026-05-01T10:00:00.000Z") -> dict:
    return message_line({"role": "user", "content": [{"type": "text", "text": text}]}, timestamp)


def assistant_line(
    content: list | None = None, timestamp="2026-05-01T10:00:05.000Z", model="qwen38"
) -> dict:
    if content is None:
        content = [{"type": "text", "text": "hi"}]
    message = {"role": "assistant", "content": content, "model": model, "stopReason": "stop"}
    return message_line(message, timestamp)


def tool_call(call_id="c1", name="bash", arguments=None) -> dict:
    return {
        "type": "toolCall",
        "id": call_id,
        "name": name,
        "arguments": {"command": "ls"} if arguments is None else arguments,
    }


def tool_result(call_id="c1", text="out", is_error=False) -> dict:
    message = {
        "role": "toolResult",
        "toolCallId": call_id,
        "toolName": "bash",
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    return message_line(message)


class TestParse:
    def test_minimal_session(self):
        raw = jsonl(header_line(), user_line(), assistant_line())
        session = parse(raw)
        assert session.harness == "pi"
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].index == 0
        assert session.turns[1].role == "assistant"
        assert session.turns[1].index == 1

    def test_model_from_assistant_message(self):
        raw = jsonl(header_line(), model_change("qwen38"), user_line(), assistant_line())
        session = parse(raw)
        assert session.models == ["qwen38"]
        assert session.turns[1].model == "qwen38"

    def test_model_selected_but_never_used_is_not_reported(self):
        """Pi records the startup default before the user has had a chance to switch."""
        raw = jsonl(
            header_line(),
            model_change("gpt-5.6"),
            model_change("qwen38"),
            user_line(),
            assistant_line(),
        )
        assert parse(raw).models == ["qwen38"]

    def test_models_are_listed_in_order_of_first_use(self):
        raw = jsonl(
            header_line(),
            user_line(),
            assistant_line(model="qwen38"),
            user_line("again"),
            assistant_line(model="gpt-5.6"),
            user_line("third"),
            assistant_line(model="qwen38"),
        )
        assert parse(raw).models == ["qwen38", "gpt-5.6"]

    def test_no_assistant_message_leaves_model_unset(self):
        raw = jsonl(header_line(), model_change("qwen38"), user_line())
        assert parse(raw).model is None

    def test_bookkeeping_entries_produce_no_turns(self):
        lines = [
            header_line(),
            entry_line("thinking_level_change", thinkingLevel="medium"),
            entry_line("session_info", name="arithmetic"),
            entry_line("label", targetId="e0", label="here"),
            entry_line("custom", customType="ext", data={}),
            entry_line("custom_message", customType="ext", content="injected", display=False),
            entry_line("compaction", summary="...", firstKeptEntryId="e0", tokensBefore=1),
            entry_line("branch_summary", summary="...", fromId="e0"),
        ]
        assert parse(jsonl(*lines)).turns == []

    def test_unknown_entry_type_warns(self, caplog):
        session = parse(jsonl(entry_line("bogus")))
        assert session.turns == []
        assert "unknown type" in caplog.text

    def test_message_entry_without_message_warns(self, caplog):
        session = parse(jsonl(entry_line("message")))
        assert session.turns == []
        assert "without a message" in caplog.text

    def test_malformed_json_skipped(self, caplog):
        raw = b"not json\n" + json.dumps(user_line()).encode()
        session = parse(raw)
        assert len(session.turns) == 1
        assert "malformed JSON" in caplog.text

    def test_empty_input(self):
        session = parse(b"")
        assert session.turns == []
        assert session.started_at is None

    def test_timestamps_from_first_and_last_turn(self):
        raw = jsonl(
            user_line(timestamp="2026-05-01T09:00:00.000Z"),
            assistant_line(timestamp="2026-05-01T09:05:00.000Z"),
        )
        session = parse(raw)
        assert session.started_at is not None
        assert session.ended_at is not None
        assert (session.ended_at - session.started_at).total_seconds() == 300


class TestAutoDetect:
    def test_detected_by_session_header(self):
        session, _ = detect_parse(jsonl(header_line(), user_line()))
        assert session.harness == "pi"

    def test_leading_whitespace_tolerated(self):
        session, _ = detect_parse(b"\n" + jsonl(header_line(), user_line()))
        assert session.harness == "pi"

    def test_codex_rollout_not_mistaken(self):
        meta = {"timestamp": "t", "type": "session_meta", "payload": {"id": "x"}}
        session, _ = detect_parse(jsonl(meta))
        assert session.harness == "codex"

    def test_claude_code_jsonl_not_mistaken(self):
        line = {"type": "user", "message": {"role": "user", "content": "hi"}}
        session, _ = detect_parse(jsonl(line))
        assert session.harness == "claude-code"


class TestUserMessages:
    def test_string_content(self):
        session = parse(jsonl(message_line({"role": "user", "content": "plain"})))
        assert session.turns[0].blocks[0].text == "plain"

    def test_empty_message_skipped(self):
        assert parse(jsonl(user_line(""))).turns == []
        assert parse(jsonl(message_line({"role": "user", "content": []}))).turns == []

    def test_multipart_message_keeps_parts(self):
        content = [
            {"type": "text", "text": "look at this"},
            {"type": "image", "data": "AAAA", "mimeType": "image/png"},
        ]
        session = parse(jsonl(message_line({"role": "user", "content": content})))
        assert [b.kind for b in session.turns[0].blocks] == ["text", "image"]

    def test_bash_execution_becomes_user_text(self):
        message = {
            "role": "bashExecution",
            "command": "git status",
            "output": "clean",
            "exitCode": 0,
            "cancelled": False,
            "truncated": False,
        }
        session = parse(jsonl(message_line(message)))
        assert session.turns[0].role == "user"
        assert session.turns[0].blocks[0].text == "Ran `git status`\n```\nclean\n```"

    def test_hidden_custom_message_skipped(self):
        message = {"role": "custom", "customType": "ext", "content": "x", "display": False}
        assert parse(jsonl(message_line(message))).turns == []

    def test_displayed_custom_message_becomes_user_text(self):
        message = {"role": "custom", "customType": "ext", "content": "injected", "display": True}
        session = parse(jsonl(message_line(message)))
        assert session.turns[0].role == "user"
        assert session.turns[0].blocks[0].text == "injected"

    def test_displayed_custom_message_entry_becomes_user_text(self):
        content = [{"type": "text", "text": "from an extension"}]
        entry = entry_line("custom_message", customType="ext", content=content, display=True)
        session = parse(jsonl(entry))
        assert session.turns[0].role == "user"
        assert session.turns[0].blocks[0].text == "from an extension"

    def test_unknown_role_warns(self, caplog):
        assert parse_message({"role": "bogus"}, 1) is None
        assert "unknown role" in caplog.text


class TestAssistantMessages:
    def test_text_and_thinking(self):
        content = [{"type": "thinking", "thinking": "hm"}, {"type": "text", "text": "hi"}]
        session = parse(jsonl(assistant_line(content)))
        blocks = session.turns[0].blocks
        assert [b.kind for b in blocks] == ["thinking", "text"]
        assert blocks[0].text == "hm"
        assert blocks[1].text == "hi"

    def test_aborted_message_with_no_content_skipped(self):
        line = assistant_line([])
        line["message"]["stopReason"] = "aborted"
        line["message"]["errorMessage"] = "Operation aborted"
        assert parse(jsonl(line)).turns == []

    def test_failed_message_surfaces_its_error(self):
        line = assistant_line([])
        line["message"]["stopReason"] = "error"
        line["message"]["errorMessage"] = "context window exceeded"
        session = parse(jsonl(line))
        assert session.turns[0].role == "assistant"
        assert session.turns[0].blocks[0].text == "Error: context window exceeded"

    def test_empty_text_part_dropped(self):
        session = parse(jsonl(assistant_line([{"type": "text", "text": ""}])))
        assert session.turns == []

    def test_unknown_part_warns(self, caplog):
        session = parse(jsonl(assistant_line([{"type": "bogus"}])))
        assert session.turns == []
        assert "unknown part type" in caplog.text


class TestToolMessages:
    def test_tool_call_arguments_are_the_input(self):
        call = tool_call(name="read", arguments={"path": "a.txt", "limit": 10})
        session = parse(jsonl(assistant_line([call])))
        block = session.turns[0].blocks[0]
        assert block.kind == "tool_use"
        assert block.tool_name == "read"
        assert block.tool_input == {"path": "a.txt", "limit": 10}
        assert block.tool_input_text is None
        assert block.tool_use_id == "c1"

    def test_tool_call_non_object_arguments_become_empty_input(self):
        session = parse(jsonl(assistant_line([tool_call(arguments="raw")])))
        assert session.turns[0].blocks[0].tool_input == {}

    def test_result_text_joined_and_error_flag_kept(self):
        message = {
            "role": "toolResult",
            "toolCallId": "c1",
            "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
            "isError": True,
        }
        parsed = parse_message(message, 1)
        assert parsed is not None
        role, blocks = parsed
        assert role == "assistant"
        assert blocks[0].kind == "tool_result"
        assert blocks[0].tool_output == "a\nb"
        assert blocks[0].is_error is True

    def test_result_image_part_gets_placeholder(self):
        message = {
            "role": "toolResult",
            "toolCallId": "c1",
            "content": [
                {"type": "text", "text": "Read image file [image/png]"},
                {"type": "image", "data": "AAAA", "mimeType": "image/png"},
            ],
            "isError": False,
        }
        parsed = parse_message(message, 1)
        assert parsed is not None
        assert parsed[1][0].tool_output == "Read image file [image/png]\n[image]"

    def test_result_ansi_stripped(self):
        session = parse(
            jsonl(assistant_line([tool_call()]), tool_result(text="\x1b[31mred\x1b[0m"))
        )
        assert session.turns[0].blocks[1].tool_output == "red"

    def test_call_and_result_pair_up(self):
        raw = jsonl(user_line(), assistant_line([tool_call()]), tool_result())
        session = parse(raw)
        assert [t.role for t in session.turns] == ["user", "assistant"]
        kinds = [b.kind for b in session.turns[1].blocks]
        assert kinds == ["tool_use", "tool_result"]

    def test_parallel_calls_each_get_their_result(self):
        raw = jsonl(
            user_line(),
            assistant_line([tool_call("c1"), tool_call("c2")]),
            tool_result("c1", "one"),
            tool_result("c2", "two"),
            assistant_line([{"type": "text", "text": "done"}]),
        )
        session = parse(raw)
        assert [t.role for t in session.turns] == ["user", "assistant", "assistant"]
        blocks = session.turns[1].blocks
        assert [(b.kind, b.tool_use_id) for b in blocks] == [
            ("tool_use", "c1"),
            ("tool_result", "c1"),
            ("tool_use", "c2"),
            ("tool_result", "c2"),
        ]
        assert [b.tool_output for b in blocks if b.kind == "tool_result"] == ["one", "two"]
        assert blocks[1].tool_name == "bash"

    def test_orphan_result_gets_its_own_turn(self):
        session = parse(jsonl(user_line(), tool_result("nope")))
        assert [t.role for t in session.turns] == ["user", "assistant"]
        assert session.turns[1].blocks[0].kind == "tool_result"


class TestHelpers:
    def test_join_result_text_ignores_malformed_parts(self):
        assert join_result_text([{"type": "text", "text": "a"}, {"type": "text"}, "x"]) == "a"

    def test_join_result_text_non_list(self):
        assert join_result_text(None) == ""

    def test_format_bash_execution_no_output(self):
        text = format_bash_execution({"command": "true", "output": "", "exitCode": 0})
        assert text == "Ran `true`\n(no output)"

    def test_format_bash_execution_exit_code(self):
        text = format_bash_execution({"command": "false", "output": "x", "exitCode": 1})
        assert text.endswith("Command exited with code 1")

    def test_format_bash_execution_truncated(self):
        message = {"command": "cat big", "output": "x", "exitCode": 0, "truncated": True}
        assert format_bash_execution(message).endswith("[Output truncated]")

    def test_format_bash_execution_cancelled(self):
        text = format_bash_execution({"command": "sleep 9", "output": "", "cancelled": True})
        assert text.endswith("(command cancelled)")


class TestFixtureSmoke:
    @pytest.fixture(
        params=[
            "2026-08-26T01-14-47-646Z_01a03ba2-4dde-7bbd-9420-8627d068e088.jsonl",
            "2026-09-14T17-00-47-986Z_01a0a0dd-39f2-73ea-ab16-e09dcdd32d87.jsonl",
            "2026-09-14T17-00-54-319Z_01a0a0dd-52af-72a6-b760-4d2a9883179b.jsonl",
        ]
    )
    def session(self, request, pi_fixtures_dir):
        fixture = pi_fixtures_dir / request.param
        return parse(fixture.read_bytes())

    def test_has_turns(self, session):
        assert len(session.turns) > 0

    def test_harness(self, session):
        assert session.harness == "pi"

    def test_metadata_populated(self, session):
        assert session.model == "qwen38"
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


class TestFixtureDetails:
    def test_all_fixtures_auto_detected(self, pi_fixtures_dir):
        for fixture in pi_fixtures_dir.iterdir():
            detected, _ = detect_parse(fixture.read_bytes())
            assert detected.harness == "pi"

    def test_no_tools(self, pi_fixtures_dir):
        fixture = "2026-08-26T01-14-47-646Z_01a03ba2-4dde-7bbd-9420-8627d068e088.jsonl"
        session = parse((pi_fixtures_dir / fixture).read_bytes())
        assert [t.role for t in session.turns] == ["user", "assistant"]
        assert [b.kind for b in session.turns[1].blocks] == ["thinking", "text"]

    def test_startup_model_change_is_not_reported_when_the_user_switched_first(
        self, pi_fixtures_dir
    ):
        """Pi logs the default model at startup, here switched away from before any prompt."""
        fixture = "2026-09-16T15-55-54-213Z_01a0aaee-87e5-7a41-8f78-5d772f26fa83.jsonl"
        session = parse((pi_fixtures_dir / fixture).read_bytes())
        assert session.models == ["nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16"]

    def test_aborted_session_keeps_only_the_prompt(self, pi_fixtures_dir):
        fixture = "2026-09-01T19-27-01-466Z_01a05e70-6d5a-706e-b84c-94bd628d450d.jsonl"
        session = parse((pi_fixtures_dir / fixture).read_bytes())
        assert [t.role for t in session.turns] == ["user"]
        assert session.turns[0].blocks[0].text == "/clear"

    def test_tool_session_pairs_every_result_with_its_call(self, pi_fixtures_dir):
        fixture = "2026-09-14T17-00-47-986Z_01a0a0dd-39f2-73ea-ab16-e09dcdd32d87.jsonl"
        session = parse((pi_fixtures_dir / fixture).read_bytes())
        kinds = Counter(b.kind for t in session.turns for b in t.blocks)
        assert kinds["tool_use"] == 3
        assert kinds["tool_result"] == 3
        for turn in session.turns:
            if turn.blocks[0].kind == "tool_result":
                pytest.fail("a tool result was not merged into its calling turn")
        errors = [b for t in session.turns for b in t.blocks if b.is_error]
        assert len(errors) == 1
        assert "ENOENT" in (errors[0].tool_output or "")
        assert [b.kind for b in session.turns[1].blocks] == ["thinking", "tool_use", "tool_result"]
        assert session.turns[1].blocks[1].tool_name == "read"
        assert session.turns[1].blocks[2].tool_name == "read"

    def test_resumed_session_has_two_prompts(self, pi_fixtures_dir):
        fixture = "2026-09-14T17-00-54-319Z_01a0a0dd-52af-72a6-b760-4d2a9883179b.jsonl"
        session = parse((pi_fixtures_dir / fixture).read_bytes())
        assert [t.role for t in session.turns] == ["user", "assistant", "user", "assistant"]
        assert session.turns[3].blocks[-1].text == "4 multiplied by 3 equals 12."
