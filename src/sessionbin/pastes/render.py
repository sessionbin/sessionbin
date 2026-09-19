from dataclasses import dataclass
from datetime import datetime

from django.template.loader import render_to_string

from sessionbin.schema.types import Session, Turn

RENDERER_VERSION = 6

# Idle long enough that a reader would want to know the session stopped and resumed.
IDLE_GAP_SECONDS = 3600


def render(session: Session) -> str:
    return render_to_string(
        "pastes/transcript.html",
        {
            "session": session,
            "stats": _compute_stats(session),
            "prompts": build_prompt_index(session),
        },
    )


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


def _compute_stats(session: Session) -> dict:
    duration = None
    if session.started_at and session.ended_at:
        duration = (session.ended_at - session.started_at).total_seconds()
    return {
        "turn_count": session.turn_count,
        "tool_call_count": session.tool_call_count,
        "duration": duration,
    }
