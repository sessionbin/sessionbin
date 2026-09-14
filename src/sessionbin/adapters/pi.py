import json
import logging

from sessionbin.adapters.common import attach_results, find_call_turn, parse_timestamp, strip_ansi
from sessionbin.schema.types import Block, Role, Session, Turn

ADAPTER_VERSION = 1

logger = logging.getLogger(__name__)

SKIPPED_ENTRY_TYPES = frozenset(
    {
        "session",
        "thinking_level_change",
        "session_info",
        "label",
        "custom",
        "compaction",
        "branch_summary",
    }
)


def parse(raw: bytes) -> Session:
    session = Session(harness="pi")
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

        entry_type = obj.get("type")

        if entry_type == "model_change":
            if session.model is None and obj.get("modelId"):
                session.model = obj["modelId"]
            continue

        if entry_type == "custom_message":
            parsed = parse_custom(obj, lineno)
        elif entry_type == "message":
            message = obj.get("message")
            if not isinstance(message, dict):
                logger.warning("skipping line %d without a message", lineno)
                continue
            if session.model is None and message.get("role") == "assistant":
                session.model = message.get("model") or None
            parsed = parse_message(message, lineno)
        else:
            if entry_type not in SKIPPED_ENTRY_TYPES:
                logger.warning("skipping unknown type %r on line %d", entry_type, lineno)
            continue
        if parsed is None:
            continue
        role, blocks = parsed
        if call_turn := find_call_turn(turns, blocks):
            attach_results(call_turn, blocks)
            continue
        turns.append(
            Turn(
                index=len(turns),
                role=role,
                timestamp=parse_timestamp(obj.get("timestamp")),
                blocks=blocks,
            )
        )

    session.turns = turns
    return session


def parse_message(message: dict, lineno: int) -> tuple[Role, list[Block]] | None:
    role = message.get("role")

    if role == "user":
        blocks = parse_content(message.get("content"), lineno)
        return ("user", blocks) if blocks else None

    if role == "assistant":
        blocks = parse_content(message.get("content"), lineno)
        if not blocks and message.get("stopReason") == "error" and message.get("errorMessage"):
            blocks = [Block(kind="text", text=f"Error: {message['errorMessage']}")]
        return ("assistant", blocks) if blocks else None

    if role == "toolResult":
        return "assistant", [
            Block(
                kind="tool_result",
                tool_use_id=message.get("toolCallId"),
                tool_output=strip_ansi(join_result_text(message.get("content"))),
                is_error=bool(message.get("isError")),
            )
        ]

    if role == "bashExecution":
        return "user", [Block(kind="text", text=format_bash_execution(message))]

    if role == "custom":
        return parse_custom(message, lineno)

    logger.warning("skipping unknown role %r on line %d", role, lineno)
    return None


def parse_custom(item: dict, lineno: int) -> tuple[Role, list[Block]] | None:
    """An extension-injected message, which Pi shows in the TUI only when display is set."""
    if not item.get("display"):
        return None
    blocks = parse_content(item.get("content"), lineno)
    return ("user", blocks) if blocks else None


def parse_content(content, lineno: int) -> list[Block]:
    if isinstance(content, str):
        return [Block(kind="text", text=content)] if content else []
    if not isinstance(content, list):
        return []

    blocks: list[Block] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            if part.get("text"):
                blocks.append(Block(kind="text", text=part["text"]))
        elif part_type == "thinking":
            blocks.append(Block(kind="thinking", text=part.get("thinking", "")))
        elif part_type == "toolCall":
            arguments = part.get("arguments")
            blocks.append(
                Block(
                    kind="tool_use",
                    tool_name=part.get("name"),
                    tool_input=arguments if isinstance(arguments, dict) else {},
                    tool_use_id=part.get("id"),
                )
            )
        elif part_type == "image":
            blocks.append(Block(kind="image"))
        else:
            logger.warning("skipping unknown part type %r on line %d", part_type, lineno)
    return blocks


def join_result_text(content) -> str:
    """Flatten a tool result's parts; the read tool returns an image part for image files."""
    if not isinstance(content, list):
        return ""
    parts = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "image":
            parts.append("[image]")
        elif isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "\n".join(parts)


def format_bash_execution(message: dict) -> str:
    """Render a `!command` run from the TUI the way Pi itself shows it to the model."""
    text = f"Ran `{message.get('command', '')}`\n"
    output = strip_ansi(message.get("output") or "")
    text += f"```\n{output}\n```" if output else "(no output)"
    if message.get("cancelled"):
        text += "\n\n(command cancelled)"
    elif message.get("exitCode"):
        text += f"\n\nCommand exited with code {message['exitCode']}"
    if message.get("truncated"):
        text += "\n\n[Output truncated]"
    return text
