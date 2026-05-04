from django.template.loader import render_to_string

from sessionbin.schema.types import Session

RENDERER_VERSION = 1


def render(session: Session) -> str:
    return render_to_string(
        "pastes/transcript.html",
        {"session": session, "stats": _compute_stats(session)},
    )


def _compute_stats(session: Session) -> dict:
    duration = None
    if session.started_at and session.ended_at:
        duration = (session.ended_at - session.started_at).total_seconds()
    return {
        "turn_count": session.turn_count,
        "tool_call_count": session.tool_call_count,
        "duration": duration,
    }
