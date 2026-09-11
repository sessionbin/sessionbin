import json
import logging
from datetime import datetime, timezone

from sessionbin.schema.types import Block, Session, Turn

ADAPTER_VERSION = 1

logger = logging.getLogger(__name__)


def parse(raw: bytes) -> Session:
    return parse_doc(json.loads(raw))


def parse_doc(doc: dict) -> Session:
    info = doc["info"]

    model = None
    model_obj = info.get("model")
    if isinstance(model_obj, dict):
        model = model_obj.get("id")

    session = Session(
        harness="opencode",
        model=model,
    )

    turns: list[Turn] = []
    messages = doc.get("messages", [])

    user_msg_ids: dict[str, int] = {}

    for msg in messages:
        msg_info = msg.get("info")
        if not isinstance(msg_info, dict):
            continue
        role = msg_info.get("role")
        if not role:
            continue
        parts = msg.get("parts", [])

        if role == "assistant" and "error" in msg_info and not parts:
            continue

        parent_id = msg_info.get("parentID")
        time_info = msg_info.get("time", {})
        timestamp = parse_millis(time_info.get("created"))
        completed = parse_millis(time_info.get("completed"))

        if role == "user":
            blocks = parse_parts(parts)
            turn = Turn(
                index=len(turns),
                role="user",
                timestamp=timestamp,
                blocks=blocks,
            )
            turns.append(turn)
            msg_id = msg_info.get("id")
            if msg_id:
                user_msg_ids[msg_id] = len(turns) - 1

        elif role == "assistant":
            blocks = parse_parts(parts)
            if not blocks:
                continue

            if parent_id and parent_id in user_msg_ids:
                user_turn_idx = user_msg_ids[parent_id]
                existing_idx = None
                for i in range(user_turn_idx + 1, len(turns)):
                    if turns[i].role == "assistant":
                        existing_idx = i
                        break
                    if turns[i].role == "user":
                        break

                if existing_idx is not None:
                    turns[existing_idx].blocks.extend(blocks)
                    if completed:
                        turns[existing_idx].ended_at = completed
                    continue

            turn = Turn(
                index=len(turns),
                role="assistant",
                timestamp=timestamp,
                blocks=blocks,
                ended_at=completed,
            )
            turns.append(turn)

    session.turns = turns
    return session


def parse_millis(ms: int | float | None) -> datetime | None:
    if not isinstance(ms, int | float):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except ValueError:
        return None


def parse_parts(parts: list[dict]) -> list[Block]:
    blocks: list[Block] = []
    for part in parts:
        part_type = part.get("type")

        if part_type == "text":
            text = part.get("text", "")
            if text:
                blocks.append(Block(kind="text", text=text))

        elif part_type == "reasoning":
            text = part.get("text", "")
            if text:
                blocks.append(Block(kind="thinking", text=text))

        elif part_type == "tool":
            tool_name = part.get("tool")
            call_id = part.get("callID")
            state = part.get("state", {})
            tool_input = state.get("input")

            blocks.append(
                Block(
                    kind="tool_use",
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_use_id=call_id,
                )
            )

            status = state.get("status")
            if status in ("completed", "error"):
                output = state.get("output") or state.get("error", "")
                blocks.append(
                    Block(
                        kind="tool_result",
                        tool_use_id=call_id,
                        tool_output=output,
                        is_error=status == "error",
                    )
                )

        elif part_type in ("step-start", "step-finish", "patch", "snapshot"):
            continue

        else:
            logger.warning("skipping unknown part type %r", part_type)

    return blocks
