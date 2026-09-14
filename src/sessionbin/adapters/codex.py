import json
import logging

from sessionbin.adapters.common import find_call_turn, parse_timestamp, strip_ansi
from sessionbin.schema.types import Block, Role, Session, Turn

ADAPTER_VERSION = 1

logger = logging.getLogger(__name__)

INJECTED_USER_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<turn_aborted>",
    "<skill>",
)

SKIPPED_LINE_TYPES = frozenset(
    {
        "session_meta",
        "event_msg",
        "world_state",
        "compacted",
        "inter_agent_communication_metadata",
    }
)


def parse(raw: bytes) -> Session:
    session = Session(harness="codex")
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

        line_type = obj.get("type")
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            logger.warning("skipping line %d without a payload", lineno)
            continue

        if line_type == "turn_context":
            if session.model is None and payload.get("model"):
                session.model = payload["model"]
            continue

        if line_type != "response_item":
            if line_type not in SKIPPED_LINE_TYPES:
                logger.warning("skipping unknown type %r on line %d", line_type, lineno)
            continue

        parsed = parse_item(payload, lineno)
        if parsed is None:
            continue
        role, blocks = parsed
        if call_turn := find_call_turn(turns, blocks):
            call_turn.blocks.extend(blocks)
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


def parse_item(item: dict, lineno: int) -> tuple[Role, list[Block]] | None:
    item_type = item.get("type")

    if item_type == "message":
        role = item.get("role")
        text = join_text(item.get("content"))
        if role == "user":
            if not text or text.startswith(INJECTED_USER_PREFIXES):
                return None
            return "user", [Block(kind="text", text=text)]
        if role == "assistant":
            if not text:
                return None
            return "assistant", [Block(kind="text", text=text)]
        return None

    if item_type == "reasoning":
        parts = [join_text(item.get("summary")), join_text(item.get("content"))]
        return "assistant", [Block(kind="thinking", text="\n".join(p for p in parts if p))]

    if item_type == "function_call":
        arguments = item.get("arguments")
        try:
            tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            tool_input = None
        if not isinstance(tool_input, dict):
            tool_input = {"arguments": arguments}
        return "assistant", [
            Block(
                kind="tool_use",
                tool_name=item.get("name"),
                tool_input=tool_input,
                tool_use_id=item.get("call_id"),
            )
        ]

    if item_type == "custom_tool_call":
        return "assistant", [
            Block(
                kind="tool_use",
                tool_name=item.get("name"),
                tool_input_text=item.get("input", ""),
                tool_use_id=item.get("call_id"),
            )
        ]

    if item_type in ("function_call_output", "custom_tool_call_output"):
        output = item.get("output", "")
        if isinstance(output, list):
            output = join_text(output)
        elif not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False)
        return "assistant", [
            Block(
                kind="tool_result",
                tool_use_id=item.get("call_id"),
                tool_output=strip_ansi(output),
            )
        ]

    if item_type == "agent_message":
        return None

    logger.warning("skipping unknown item type %r on line %d", item_type, lineno)
    return None


def join_text(content) -> str:
    """Concatenate the text parts of a content list.

    Codex splits one logical text into several parts (tool output header, then body),
    so parts are joined rather than turned into separate blocks.
    """
    if not isinstance(content, list):
        return ""
    parts = [
        part["text"]
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    return "\n".join(parts)
