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


def attach_results(turn: Turn, results: list[Block]) -> None:
    """Place each result right behind its call, so a call and its output read together.

    Harnesses that batch parallel calls into one message stream every result after all
    the calls; appending would push each output several blocks away from its call. A
    duplicated call id (seen from Qwen through Pi) pairs up in order: the first copy
    without a result takes the next one, and the last copy collects any extras.
    """
    for result in results:
        calls = [
            i
            for i, b in enumerate(turn.blocks)
            if b.kind == "tool_use" and b.tool_use_id == result.tool_use_id
        ]
        unanswered = [
            i
            for i in calls
            if i + 1 == len(turn.blocks) or turn.blocks[i + 1].kind != "tool_result"
        ]
        call = unanswered[0] if unanswered else calls[-1]
        at = call + 1
        while at < len(turn.blocks) and turn.blocks[at].kind == "tool_result":
            at += 1
        result.tool_name = turn.blocks[call].tool_name
        turn.blocks.insert(at, result)


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)
