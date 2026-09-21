import json

import mistune
from django import template
from django.utils.safestring import mark_safe
from mistune.plugins.url import parse_url_link
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from sessionbin.pastes.render import is_blank_thinking

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


# mistune's own url plugin stops a bare link on `. , : ; " ' ) ]` but not on `*` or `_`,
# so `**https://example.com/**` hands its closing delimiter to the href: the link breaks
# and the emphasis never pairs. GFM's autolink extension leaves both out, so do the same.
URL_LINK_PATTERN = r"""https?:\/\/[^\s<]+[^<.,:;"')\]\s*_]"""


def url_without_trailing_emphasis(md: mistune.Markdown) -> None:
    md.inline.register("url_link", URL_LINK_PATTERN, parse_url_link)


_markdown = mistune.create_markdown(
    escape=True,
    renderer=_HighlightRenderer(),
    plugins=[url_without_trailing_emphasis, "table"],
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
def text_summary(text: str | None) -> str:
    """One-line preview for a collapsed thinking block or free-text tool input.

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
    """A span of time, coarsening as it grows.

    Sessions run for hours and are put down and picked up again, so past an hour the
    seconds stop carrying information and only make the number harder to read.
    """
    if seconds is None:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
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


@register.filter
def visible_blocks(turn) -> list:
    """Blocks that have something to show.

    Models defaulting to omitted reasoning display still emit thinking blocks, but with
    empty text. Rendering those produces blank boxes, so drop them here.
    """
    return [b for b in turn.blocks if not is_blank_thinking(b)]
