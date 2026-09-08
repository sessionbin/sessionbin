from datetime import datetime, timezone

from sessionbin.pastes.render import (
    _compute_stats,
    render,
)
from sessionbin.pastes.templatetags.transcript import (
    duration,
    highlight_json,
    render_markdown,
    tool_summary,
)
from sessionbin.schema.types import Block, Session, Turn


class TestToolSummary:
    def test_short(self):
        assert tool_summary({"a": 1}) == '{"a": 1}'

    def test_long_truncated(self):
        d = {"key": "x" * 100}
        result = tool_summary(d)
        assert len(result) == 80
        assert result.endswith("...")

    def test_none(self):
        assert tool_summary(None) == ""

    def test_empty_dict(self):
        assert tool_summary({}) == ""


class TestHighlightJson:
    def test_dict(self):
        result = highlight_json({"command": "ls"})
        assert 'class="highlight"' in result
        assert "command" in result
        assert "ls" in result

    def test_none(self):
        assert highlight_json(None) == ""


class TestFormatDuration:
    def test_none(self):
        assert duration(None) == "?"

    def test_seconds_only(self):
        assert duration(45) == "45s"

    def test_minutes_and_seconds(self):
        assert duration(125) == "2m 5s"

    def test_zero(self):
        assert duration(0) == "0s"


class TestComputeStats:
    def test_with_turns_and_tool_calls(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
        turns = [
            Turn(
                index=0,
                role="user",
                timestamp=t0,
                blocks=[
                    Block(kind="text", text="hi"),
                ],
            ),
            Turn(
                index=1,
                role="assistant",
                timestamp=t1,
                blocks=[
                    Block(kind="tool_use", tool_name="Bash"),
                    Block(kind="tool_use", tool_name="Read"),
                ],
            ),
        ]
        session = Session(
            harness="claude-code",
            turns=turns,
        )
        stats = _compute_stats(session)
        assert stats["turn_count"] == 2
        assert stats["tool_call_count"] == 2
        assert stats["duration"] == 60.0

    def test_empty_session(self):
        session = Session(harness="claude-code")
        stats = _compute_stats(session)
        assert stats["turn_count"] == 0
        assert stats["tool_call_count"] == 0
        assert stats["duration"] is None

    def test_duration_uses_last_turn_end(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
        turns = [
            Turn(index=0, role="user", timestamp=t0),
            Turn(index=1, role="assistant", timestamp=t1, ended_at=end),
        ]
        session = Session(harness="opencode", turns=turns)
        stats = _compute_stats(session)
        assert stats["duration"] == 300.0


class TestRenderMarkdown:
    def test_plain_text(self):
        result = render_markdown("hello world")
        assert "<p>hello world</p>" in result

    def test_bold(self):
        result = render_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = render_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_inline_code(self):
        result = render_markdown("`foo`")
        assert "<code>foo</code>" in result

    def test_fenced_code_with_language(self):
        result = render_markdown("```python\nprint('hi')\n```")
        assert 'class="highlight"' in result
        assert "print" in result

    def test_fenced_code_without_language(self):
        result = render_markdown("```\nsome code\n```")
        assert "<pre><code>" in result
        assert "some code" in result

    def test_fenced_code_unknown_language(self):
        result = render_markdown("```notareallanguage\ncode\n```")
        assert "<pre><code>" in result

    def test_unordered_list(self):
        result = render_markdown("- one\n- two")
        assert "<ul>" in result
        assert "<li>" in result

    def test_ordered_list(self):
        result = render_markdown("1. one\n2. two")
        assert "<ol>" in result

    def test_raw_html_escaped(self):
        result = render_markdown('<script>alert("xss")</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_none_returns_empty(self):
        assert render_markdown(None) == ""

    def test_empty_returns_empty(self):
        assert render_markdown("") == ""


class TestRender:
    def test_minimal_session(self):
        session = Session(
            harness="claude-code",
            turns=[
                Turn(
                    index=0,
                    role="user",
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    blocks=[Block(kind="text", text="hello")],
                ),
            ],
        )
        html = render(session)
        assert '<div class="transcript">' in html
        assert "claude-code" in html
        assert "hello" in html

    def test_all_block_types(self):
        session = Session(
            harness="claude-code",
            turns=[
                Turn(
                    index=0,
                    role="user",
                    timestamp=None,
                    blocks=[
                        Block(kind="text", text="do something"),
                    ],
                ),
                Turn(
                    index=1,
                    role="assistant",
                    timestamp=None,
                    blocks=[
                        Block(kind="thinking", text="let me think"),
                        Block(kind="tool_use", tool_name="Bash", tool_input={"cmd": "ls"}),
                        Block(kind="tool_result", tool_output="file.txt", tool_use_id="t1"),
                        Block(kind="text", text="done"),
                    ],
                ),
            ],
        )
        html = render(session)
        assert "do something" in html
        assert "let me think" in html
        assert "Bash" in html
        assert "file.txt" in html
        assert "done" in html

    def test_text_block_renders_markdown(self):
        session = Session(
            harness="claude-code",
            turns=[
                Turn(
                    index=0,
                    role="assistant",
                    timestamp=None,
                    blocks=[
                        Block(kind="text", text="**bold** and `code`"),
                    ],
                ),
            ],
        )
        html = render(session)
        assert "<strong>bold</strong>" in html
        assert "<code>code</code>" in html
        assert 'class="block-text"' in html

    def test_text_block_syntax_highlighting(self):
        session = Session(
            harness="claude-code",
            turns=[
                Turn(
                    index=0,
                    role="assistant",
                    timestamp=None,
                    blocks=[
                        Block(kind="text", text='```python\nprint("hello")\n```'),
                    ],
                ),
            ],
        )
        html = render(session)
        assert 'class="highlight"' in html

    def test_empty_session(self):
        session = Session(harness="claude-code")
        html = render(session)
        assert '<div class="transcript">' in html
        assert "claude-code" in html

    def _render_turn(self, *blocks):
        session = Session(
            harness="claude-code",
            turns=[Turn(index=0, role="assistant", timestamp=None, blocks=list(blocks))],
        )
        return render(session)

    def test_thinking_with_text_is_collapsible(self):
        html = self._render_turn(Block(kind="thinking", text="weighing the options"))
        assert 'class="thinking-details"' in html
        assert "<summary>thinking — weighing the options</summary>" in html
        assert "weighing the options" in html
        assert "turn-omitted" not in html

    def test_thinking_summary_previews_first_line_only(self):
        html = self._render_turn(
            Block(kind="thinking", text="first line\n\nsecond line with more detail")
        )
        assert "<summary>thinking — first line</summary>" in html
        # The body still carries the whole thing.
        assert "second line with more detail" in html

    def test_turn_of_only_empty_thinking_collapses_to_one_line(self):
        # Opus 4.7+ and Sonnet 5 default to thinking display "omitted", so the block
        # arrives with a signature but no text. Claude Code streams one block per line,
        # so it would otherwise be a whole turn card wrapped around nothing.
        for empty in ("", "   \n  "):
            html = self._render_turn(Block(kind="thinking", text=empty))
            assert 'class="turn-omitted"' in html
            assert ">thinking<" in html
            assert 'class="turn role-assistant"' not in html
            assert 'class="turn-body"' not in html
            assert 'class="thinking-details"' not in html

    def test_empty_thinking_dropped_from_a_turn_that_has_other_content(self):
        html = self._render_turn(
            Block(kind="thinking", text=""),
            Block(kind="text", text="the answer"),
        )
        assert "the answer" in html
        assert 'class="turn role-assistant"' in html
        assert "turn-omitted" not in html
        assert 'class="thinking-details"' not in html

    def test_turn_with_no_blocks_still_renders_its_header(self):
        html = self._render_turn()
        assert 'class="turn role-assistant"' in html
        assert "turn-omitted" not in html
