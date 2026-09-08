import json

import mistune
from django import template
from django.utils.safestring import mark_safe
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

register = template.Library()

_pygments_formatter = HtmlFormatter(nowrap=False, cssclass="highlight")


_json_lexer = get_lexer_by_name("json", stripall=True)


class _HighlightRenderer(mistune.HTMLRenderer):
    def block_code(self, code: str, info: str | None = None) -> str:
        if not info:
            return "<pre><code>" + mistune.escape(code) + "</code></pre>\n"
        lang = info.split(None, 1)[0]
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            return "<pre><code>" + mistune.escape(code) + "</code></pre>\n"
        return pygments_highlight(code, lexer, _pygments_formatter)


_markdown = mistune.create_markdown(
    escape=True, renderer=_HighlightRenderer(), plugins=["url", "table"]
)


@register.filter
def tool_summary(value: dict | None) -> str:
    if not value:
        return ""
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > 80:
        return text[:77] + "..."
    return text


@register.filter
def thinking_summary(text: str | None) -> str:
    """One-line preview for a collapsed thinking block.

    Mirrors tool_summary: enough to scan without expanding.
    """
    if not text:
        return ""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first) > 80:
        return first[:77] + "..."
    return first


@register.filter
def duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


@register.filter
def highlight_json(value: dict | None) -> str:
    if value is None:
        return ""
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return mark_safe(pygments_highlight(text, _json_lexer, _pygments_formatter))


@register.filter
def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    result = _markdown(text)
    assert isinstance(result, str)
    return mark_safe(result)


def _is_blank_thinking(block) -> bool:
    return block.kind == "thinking" and not (block.text or "").strip()


@register.filter
def visible_blocks(turn) -> list:
    """Blocks that have something to show.

    Models defaulting to omitted reasoning display still emit thinking blocks, but with
    empty text. Rendering those produces blank boxes, so drop them here.
    """
    return [b for b in turn.blocks if not _is_blank_thinking(b)]


@register.filter
def is_omitted_thinking_turn(turn) -> bool:
    """True when a turn's only content was thinking that the model did not record.

    Claude Code streams one block per line, so each such block becomes an entire turn.
    The template collapses these to a single line instead of a full turn card.
    """
    return bool(turn.blocks) and all(_is_blank_thinking(b) for b in turn.blocks)
