import json
import logging
import re
from datetime import datetime

from sessionbin.schema.types import Block, Session, Turn

ADAPTER_VERSION = 1

logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>")
_LOCAL_STDOUT_RE = re.compile(r"<local-command-stdout>(.*)</local-command-stdout>", re.DOTALL)


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

        content = message.get("content", "")

        if msg_type == "user" and isinstance(content, str):
            content = _process_user_text(content)
            if content is None:
                continue

        blocks = _parse_content(content, lineno)

        turn = Turn(
            index=len(turns),
            role=role,
            timestamp=timestamp,
            blocks=blocks,
        )
        turns.append(turn)

    session.turns = turns
    return session


def _process_user_text(text: str) -> str | None:
    if text.startswith("<local-command-caveat>"):
        return None

    if m := _COMMAND_NAME_RE.search(text):
        return f"`{m.group(1)}`"

    if m := _LOCAL_STDOUT_RE.search(text):
        return m.group(1)

    return text


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def _parse_content(content, lineno: int) -> list[Block]:
    if isinstance(content, str):
        if content:
            return [Block(kind="text", text=_strip_ansi(content))]
        return []

    if not isinstance(content, list):
        return []

    blocks: list[Block] = []
    for item in content:
        block_type = item.get("type")
        if block_type == "text":
            blocks.append(Block(kind="text", text=_strip_ansi(item.get("text", ""))))
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
                    tool_output=_strip_ansi(output),
                    is_error=item.get("is_error", False),
                )
            )
        elif block_type == "image":
            blocks.append(Block(kind="image"))
        else:
            logger.warning("skipping unknown block type %r on line %d", block_type, lineno)

    return blocks
