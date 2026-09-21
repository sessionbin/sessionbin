from dataclasses import dataclass
from datetime import datetime

from django.template.loader import render_to_string

from sessionbin.schema.types import Block, Session, Turn

RENDERER_VERSION = 9

# Idle long enough that a reader would want to know the session stopped and resumed.
IDLE_GAP_SECONDS = 3600


def render(session: Session) -> str:
    return render_to_string(
        "pastes/transcript.html",
        {
            "session": session,
            "stats": compute_stats(session),
            "prompts": build_prompt_index(session),
            "rows": build_rows(session),
        },
    )


@dataclass
class OmittedThinking:
    """Consecutive turns whose only content was reasoning the model did not record.

    `is_thinking_run` is what the template branches on, since it cannot ask what type a
    row is. A run of one renders exactly as a single turn always did.
    """

    count: int
    started_at: datetime | None
    ended_at: datetime | None
    is_thinking_run: bool = True


def is_blank_thinking(block: Block) -> bool:
    return block.kind == "thinking" and not (block.text or "").strip()


def is_omitted_thinking_turn(turn: Turn) -> bool:
    """True when a turn's only content was thinking that the model did not record."""
    return bool(turn.blocks) and all(is_blank_thinking(b) for b in turn.blocks)


def build_rows(session: Session) -> list[Turn | OmittedThinking]:
    """The session's turns, with unrecorded reasoning gathered into runs.

    Codex returns its reasoning encrypted and its summary empty, so a session can carry a
    long stretch of turns that each have nothing to say. Given a row apiece they repeat
    the same nothing down the page, so consecutive ones become one row that reports how
    many there were and how long they took.
    """
    rows: list[Turn | OmittedThinking] = []
    for turn in session.turns:
        if not is_omitted_thinking_turn(turn):
            rows.append(turn)
            continue
        last = rows[-1] if rows else None
        if isinstance(last, OmittedThinking):
            last.count += 1
            last.ended_at = turn.timestamp or last.ended_at
        else:
            rows.append(
                OmittedThinking(count=1, started_at=turn.timestamp, ended_at=turn.timestamp)
            )
    return rows


@dataclass
class Prompt:
    """One user turn, as the transcript's navigator lists it.

    `gap` is the idle time before the prompt, set only when it is long enough to be
    worth showing.
    """

    index: int
    timestamp: datetime | None
    text: str
    gap: float | None


def build_prompt_index(session: Session) -> list[Prompt]:
    """The session's user prompts, for the transcript's jump-to navigator.

    Only user turns are indexed. A session runs to hundreds of turns but holds a handful
    of prompts, and those are what a reader scrolling a transcript is looking for.
    """
    prompts = []
    previous_end = None
    for turn in session.turns:
        if turn.role == "user":
            text = first_text(turn)
            if text:
                gap = None
                if previous_end and turn.timestamp:
                    idle = (turn.timestamp - previous_end).total_seconds()
                    if idle >= IDLE_GAP_SECONDS:
                        gap = idle
                prompts.append(
                    Prompt(index=turn.index, timestamp=turn.timestamp, text=text, gap=gap)
                )
        if turn.timestamp:
            previous_end = turn.ended_at or turn.timestamp
    return prompts


def first_text(turn: Turn) -> str:
    for block in turn.blocks:
        if block.kind == "text" and block.text and block.text.strip():
            return block.text.strip()
    return ""


def compute_stats(session: Session) -> dict:
    duration = None
    if session.started_at and session.ended_at:
        duration = (session.ended_at - session.started_at).total_seconds()
    return {
        "turn_count": session.turn_count,
        "tool_call_count": session.tool_call_count,
        "duration": duration,
    }
