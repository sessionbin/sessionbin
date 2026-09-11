from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

BlockKind = Literal["text", "thinking", "tool_use", "tool_result", "image"]
Role = Literal["user", "assistant", "system"]


@dataclass
class Block:
    kind: BlockKind
    text: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_use_id: str | None = None
    tool_output: str | None = None
    is_error: bool = False


@dataclass
class Turn:
    index: int
    role: Role
    timestamp: datetime | None
    blocks: list[Block] = field(default_factory=list)
    # When a harness reports a turn's completion time separately from its start.
    # Harnesses that stream one turn per message leave this unset.
    ended_at: datetime | None = None


@dataclass
class Session:
    harness: str
    turns: list[Turn] = field(default_factory=list)
    model: str | None = None

    @property
    def started_at(self) -> datetime | None:
        return self.turns[0].timestamp if self.turns else None

    @property
    def ended_at(self) -> datetime | None:
        if not self.turns:
            return None
        last = self.turns[-1]
        return last.ended_at or last.timestamp

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def tool_call_count(self) -> int:
        return sum(1 for t in self.turns for b in t.blocks if b.kind == "tool_use")
