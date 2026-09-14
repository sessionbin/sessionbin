import re
from datetime import datetime

from sessionbin.schema.types import Block, Turn

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def find_call_turn(turns: list[Turn], blocks: list[Block]) -> Turn | None:
    """The trailing assistant turn whose tool calls these result blocks answer.

    Harnesses stream every result after all parallel calls, so the match can sit a few
    assistant turns back. The search stops at the previous user turn.
    """
    if not blocks or not all(b.kind == "tool_result" and b.tool_use_id for b in blocks):
        return None
    ids = {b.tool_use_id for b in blocks}
    for turn in reversed(turns):
        if turn.role != "assistant":
            return None
        if ids <= {b.tool_use_id for b in turn.blocks if b.kind == "tool_use"}:
            return turn
    return None


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)
