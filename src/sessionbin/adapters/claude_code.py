import json
import logging
from datetime import datetime

from sessionbin.schema.types import Block, Session, Turn

ADAPTER_VERSION = 1

logger = logging.getLogger(__name__)


def parse(raw: bytes) -> Session:
    session = Session(harness="claude-code")
    turns: list[Turn] = []

    for lineno, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("skipping malformed JSON on line %d", lineno)
            continue

        msg_type = obj.get("type")
        if msg_type not in ("user", "assistant"):
            if msg_type not in (
                "system",
                "file-history-snapshot",
                "last-prompt",
                "permission-mode",
                "attachment",
                "queue-operation",
                "custom-title",
                "agent-name",
            ):
                logger.warning("skipping unknown type %r on line %d", msg_type, lineno)
            continue

        timestamp = _parse_timestamp(obj.get("timestamp"))

        if session.cwd is None and obj.get("cwd"):
            session.cwd = obj["cwd"]
        if session.git_branch is None and obj.get("gitBranch"):
            session.git_branch = obj["gitBranch"]

        message = obj.get("message", {})
        role = message.get("role", msg_type)

        if msg_type == "assistant" and session.model is None:
            model = message.get("model")
            if model:
                session.model = model

        blocks = _parse_content(message.get("content", ""), lineno)

        turn = Turn(
            index=len(turns),
            role=role,
            timestamp=timestamp,
            blocks=blocks,
        )
        turns.append(turn)

    session.turns = turns
    return session


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_content(content, lineno: int) -> list[Block]:
    if isinstance(content, str):
        if content:
            return [Block(kind="text", text=content)]
        return []

    if not isinstance(content, list):
        return []

    blocks: list[Block] = []
    for item in content:
        block_type = item.get("type")
        if block_type == "text":
            blocks.append(Block(kind="text", text=item.get("text", "")))
        elif block_type == "thinking":
            blocks.append(Block(kind="thinking", text=item.get("thinking", "")))
        elif block_type == "tool_use":
            blocks.append(
                Block(
                    kind="tool_use",
                    tool_name=item.get("name"),
                    tool_input=item.get("input"),
                    tool_use_id=item.get("id"),
                )
            )
        elif block_type == "tool_result":
            output = item.get("content", "")
            if isinstance(output, list):
                parts = [sub.get("text", "") for sub in output if sub.get("type") == "text"]
                output = "\n".join(parts)
            blocks.append(
                Block(
                    kind="tool_result",
                    tool_use_id=item.get("tool_use_id"),
                    tool_output=output,
                    is_error=item.get("is_error", False),
                )
            )
        elif block_type == "image":
            blocks.append(Block(kind="image"))
        else:
            logger.warning("skipping unknown block type %r on line %d", block_type, lineno)

    return blocks
