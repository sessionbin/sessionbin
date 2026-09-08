import json

from sessionbin.adapters import claude_code, opencode
from sessionbin.schema.types import Session

ADAPTERS: dict[str, tuple] = {
    "claude-code": (claude_code.parse, claude_code.ADAPTER_VERSION),
    "opencode": (opencode.parse, opencode.ADAPTER_VERSION),
}


def parse(raw: bytes, harness: str | None = None) -> tuple[Session, int]:
    if harness is not None:
        parse_fn, version = ADAPTERS[harness]
        return parse_fn(raw), version
    return auto_detect(raw)


def auto_detect(raw: bytes) -> tuple[Session, int]:
    stripped = raw.lstrip()
    if stripped.startswith(b"{"):
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(doc, dict) and "info" in doc and "messages" in doc:
                return opencode.parse_doc(doc), opencode.ADAPTER_VERSION
    return claude_code.parse(raw), claude_code.ADAPTER_VERSION
