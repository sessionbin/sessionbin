import re
from datetime import datetime, timedelta, timezone

from sessionbin.pastes.render import (
    OmittedThinking,
    build_prompt_index,
    build_rows,
    compute_stats,
    first_text,
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

    def test_hours_drop_seconds(self):
        assert duration(25322) == "7h 2m"

    def test_exact_hour(self):
        assert duration(3600) == "1h 0m"

    def test_just_under_an_hour_keeps_seconds(self):
        assert duration(3599) == "59m 59s"


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
        stats = compute_stats(session)
        assert stats["turn_count"] == 2
        assert stats["tool_call_count"] == 2
        assert stats["duration"] == 60.0

    def test_empty_session(self):
        session = Session(harness="claude-code")
        stats = compute_stats(session)
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
        stats = compute_stats(session)
        assert stats["duration"] == 300.0


class TestBuildPromptIndex:
    def prompts(self, *texts, gap_minutes=0):
        turns = []
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i, text in enumerate(texts):
            if i and gap_minutes:
                moment += timedelta(minutes=gap_minutes)
            else:
                moment += timedelta(seconds=30)
            turns.append(
                Turn(index=i, role="user", timestamp=moment, blocks=[Block(kind="text", text=text)])
            )
        return build_prompt_index(Session(harness="claude-code", turns=turns))

    def test_indexes_user_turns_only(self):
        turns = [
            Turn(index=0, role="user", timestamp=None, blocks=[Block(kind="text", text="do it")]),
            Turn(
                index=1,
                role="assistant",
                timestamp=None,
                blocks=[Block(kind="text", text="done")],
            ),
        ]
        prompts = build_prompt_index(Session(harness="claude-code", turns=turns))
        assert [p.index for p in prompts] == [0]
        assert prompts[0].text == "do it"

    def test_keeps_slash_commands(self):
        assert [p.text for p in self.prompts("`/clear`", "real prompt")] == [
            "`/clear`",
            "real prompt",
        ]

    def test_skips_turns_without_text(self):
        turns = [Turn(index=0, role="user", timestamp=None, blocks=[Block(kind="image")])]
        assert build_prompt_index(Session(harness="claude-code", turns=turns)) == []

    def test_marks_a_long_idle_gap(self):
        prompts = self.prompts("first", "second", gap_minutes=90)
        assert prompts[0].gap is None
        assert prompts[1].gap == 5400.0

    def test_leaves_short_gaps_unmarked(self):
        prompts = self.prompts("first", "second", gap_minutes=5)
        assert [p.gap for p in prompts] == [None, None]

    def test_gap_at_the_threshold_is_marked(self):
        prompts = self.prompts("first", "second", gap_minutes=60)
        assert prompts[1].gap == 3600.0

    def test_assistant_only_session_has_no_prompts(self):
        turns = [
            Turn(index=0, role="assistant", timestamp=None, blocks=[Block(kind="text", text="hi")])
        ]
        assert build_prompt_index(Session(harness="codex", turns=turns)) == []

    def test_gap_measures_from_a_merged_turn_end(self):
        """OpenCode merges several messages into one turn, so idle time runs from its end."""
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        turns = [
            Turn(index=0, role="user", timestamp=start, blocks=[Block(kind="text", text="go")]),
            Turn(
                index=1,
                role="assistant",
                timestamp=start + timedelta(minutes=1),
                ended_at=start + timedelta(minutes=50),
                blocks=[Block(kind="text", text="done")],
            ),
            Turn(
                index=2,
                role="user",
                timestamp=start + timedelta(minutes=100),
                blocks=[Block(kind="text", text="again")],
            ),
        ]
        prompts = build_prompt_index(Session(harness="opencode", turns=turns))
        # 50 minutes idle from the turn's end, not 99 from its start.
        assert prompts[1].gap is None

    def test_undated_turn_does_not_reset_the_gap_clock(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        turns = [
            Turn(index=0, role="user", timestamp=start, blocks=[Block(kind="text", text="go")]),
            Turn(index=1, role="assistant", timestamp=None, blocks=[Block(kind="text", text="?")]),
            Turn(
                index=2,
                role="user",
                timestamp=start + timedelta(minutes=90),
                blocks=[Block(kind="text", text="again")],
            ),
        ]
        prompts = build_prompt_index(Session(harness="claude-code", turns=turns))
        assert prompts[1].gap == 5400.0


class TestFirstText:
    def test_ignores_whitespace_only_blocks(self):
        turn = Turn(index=0, role="user", timestamp=None, blocks=[Block(kind="text", text="   ")])
        assert first_text(turn) == ""

    def test_finds_text_after_another_block(self):
        turn = Turn(
            index=0,
            role="user",
            timestamp=None,
            blocks=[Block(kind="image"), Block(kind="text", text="  hello  ")],
        )
        assert first_text(turn) == "hello"


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


class TestAutolinks:
    def test_bare_url_is_linked(self):
        result = render_markdown("see http://example.com/ for more")
        assert '<a href="http://example.com/">http://example.com/</a>' in result

    def test_emphasis_around_a_bare_url_still_pairs(self):
        """The delimiter must not end up inside the href.

        mistune's own url plugin stops the link on `.,:;"')]` but not on `*` or `_`, so
        it swallowed the closing delimiter: the emphasis went unpaired and the href
        picked up two asterisks.
        """
        result = render_markdown("Running at **http://example.com/**, live")
        assert '<strong><a href="http://example.com/">http://example.com/</a></strong>' in result
        assert "**" not in result

    def test_underscore_emphasis_around_a_bare_url_still_pairs(self):
        result = render_markdown("__http://example.com/__")
        assert '<strong><a href="http://example.com/">http://example.com/</a></strong>' in result

    def test_underscore_inside_a_url_is_kept(self):
        result = render_markdown("https://en.wikipedia.org/wiki/Foo_bar and on")
        assert 'href="https://en.wikipedia.org/wiki/Foo_bar"' in result

    def test_sentence_punctuation_stays_out_of_the_href(self):
        result = render_markdown("Go to http://example.com/a.")
        assert 'href="http://example.com/a"' in result


class TestBuildRows:
    def blank(self, index, second):
        return Turn(
            index=index,
            role="assistant",
            timestamp=datetime(2026, 9, 2, 12, 30, second, tzinfo=timezone.utc),
            blocks=[Block(kind="thinking", text="")],
        )

    def spoken(self, index):
        return Turn(
            index=index,
            role="assistant",
            timestamp=datetime(2026, 9, 2, 12, 31, 0, tzinfo=timezone.utc),
            blocks=[Block(kind="text", text="done")],
        )

    def test_consecutive_blank_thinking_becomes_one_row(self):
        rows = build_rows(
            Session(
                harness="codex", turns=[self.blank(0, 40), self.blank(1, 45), self.blank(2, 50)]
            )
        )
        assert len(rows) == 1
        assert isinstance(rows[0], OmittedThinking)
        assert rows[0].count == 3
        assert rows[0].started_at.second == 40
        assert rows[0].ended_at.second == 50

    def test_a_turn_with_content_breaks_the_run(self):
        rows = build_rows(
            Session(
                harness="codex",
                turns=[self.blank(0, 40), self.spoken(1), self.blank(2, 50), self.blank(3, 55)],
            )
        )
        assert [getattr(r, "count", None) for r in rows] == [1, None, 2]

    def test_turns_with_content_pass_through_untouched(self):
        turns = [self.spoken(0), self.spoken(1)]
        assert build_rows(Session(harness="codex", turns=turns)) == turns

    def test_a_run_without_timestamps_still_counts(self):
        turns = [
            Turn(
                index=i, role="assistant", timestamp=None, blocks=[Block(kind="thinking", text="")]
            )
            for i in range(2)
        ]
        rows = build_rows(Session(harness="codex", turns=turns))
        assert rows[0].count == 2
        assert rows[0].started_at is None


class TestNavigatorLinks:
    def test_every_navigator_link_has_a_turn_to_land_on(self):
        """A turn whose only content was unrecorded reasoning renders without an id.

        The navigator addresses turns by index, so anything that stops a turn emitting
        its anchor would leave the panel pointing at nothing.
        """
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        session = Session(
            harness="claude-code",
            turns=[
                Turn(index=0, role="user", timestamp=moment, blocks=[Block(kind="text", text="a")]),
                # Renders as a bare line, not a turn card, and carries no id.
                Turn(index=1, role="assistant", timestamp=moment, blocks=[Block(kind="thinking")]),
                Turn(index=2, role="user", timestamp=moment, blocks=[Block(kind="text", text="b")]),
            ],
        )
        html = render(session)
        linked = set(re.findall(r'data-prompt-link="([^"]+)"', html))
        anchors = set(re.findall(r'<div class="turn [^"]*" id="([^"]+)"', html))
        assert linked == {"turn-0", "turn-2"}
        assert linked <= anchors


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

    def test_tool_result_summary_uses_tool_name(self):
        html = self._render_turn(
            Block(kind="tool_use", tool_name="bash", tool_input={}, tool_use_id="call_abc"),
            Block(kind="tool_result", tool_name="bash", tool_use_id="call_abc", tool_output="ok"),
        )
        assert "<summary>bash → result</summary>" in html
        assert "call_abc..." not in html

    def test_tool_result_summary_falls_back_to_call_id(self):
        html = self._render_turn(
            Block(kind="tool_result", tool_use_id="call_abc", tool_output="ok")
        )
        assert "<summary>result for call_abc...</summary>" in html

    def test_error_result_summary_is_prefixed(self):
        html = self._render_turn(
            Block(
                kind="tool_result", tool_name="read", tool_use_id="c", tool_output="", is_error=True
            )
        )
        assert "<summary>Error: read → result</summary>" in html

    def test_free_text_tool_input_renders_as_plain_pre(self):
        session = Session(
            harness="codex",
            turns=[
                Turn(
                    index=0,
                    role="assistant",
                    timestamp=None,
                    blocks=[
                        Block(
                            kind="tool_use",
                            tool_name="exec",
                            tool_input_text="const r = 1;\ntext(r);",
                            tool_use_id="c1",
                        )
                    ],
                )
            ],
        )
        html = render(session)
        assert "<summary>exec(const r = 1;)</summary>" in html
        assert "<pre>const r = 1;\ntext(r);</pre>" in html
        body = html.split("</summary>", 1)[1].split("</details>", 1)[0]
        assert "highlight" not in body

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

    def _render_models(self, *models):
        session = Session(
            harness="claude-code",
            turns=[
                Turn(
                    index=i,
                    role="assistant",
                    timestamp=None,
                    blocks=[Block(kind="text", text="hi")],
                    model=model,
                )
                for i, model in enumerate(models)
            ],
        )
        return render(session)

    def test_header_lists_every_model_used(self):
        html = self._render_models("opus-4", "sonnet-4", "opus-4")
        assert '<span class="header-model">opus-4 · sonnet-4</span>' in html

    def test_turn_model_shown_only_when_the_session_used_more_than_one(self):
        assert 'class="turn-model"' not in self._render_models("opus-4", "opus-4")

        html = self._render_models("opus-4", "sonnet-4")
        assert '<span class="turn-model">opus-4</span>' in html
        assert '<span class="turn-model">sonnet-4</span>' in html

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

    def test_a_run_of_omitted_thinking_collapses_to_one_row(self):
        # Codex returns its reasoning encrypted with an empty summary, so these arrive
        # in stretches. One row each would repeat the same nothing down the page.
        start = datetime(2026, 9, 2, 12, 30, 40, tzinfo=timezone.utc)
        turns = [
            Turn(
                index=i,
                role="assistant",
                timestamp=start + timedelta(seconds=5 * i),
                blocks=[Block(kind="thinking", text="")],
            )
            for i in range(8)
        ]
        html = render(Session(harness="codex", turns=turns))
        assert html.count('class="turn-omitted"') == 1
        assert "&times;8" in html
        assert "12:30:40" in html
        assert "12:31:15" in html

    def test_a_lone_omitted_thinking_turn_gets_no_count(self):
        html = self._render_turn(Block(kind="thinking", text=""))
        assert 'class="turn-omitted"' in html
        assert "thinking-count" not in html
        assert "&times;" not in html

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

    def test_each_turn_is_linkable_by_its_index(self):
        html = self._render_models("opus-4", "sonnet-4")
        assert 'id="turn-0"' in html
        assert 'href="#turn-0"' in html
        assert 'id="turn-1"' in html
        assert 'href="#turn-1"' in html
