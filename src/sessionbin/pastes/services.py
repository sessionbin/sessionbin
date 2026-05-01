import hashlib

from django.utils import timezone
from django.utils.crypto import get_random_string

from sessionbin.adapters.claude_code import ADAPTER_VERSION, parse
from sessionbin.pastes.models import DELETE_TOKEN_LENGTH, Paste, hash_token
from sessionbin.pastes.render import RENDERER_VERSION, render
from sessionbin.security.redact import redact_secrets
from sessionbin.storage.factory import get_storage


def create_paste_from_upload(
    *,
    raw: bytes,
    uploader_ip: str | None,
) -> tuple[Paste, str]:
    redacted = redact_secrets(raw)
    session = parse(redacted)
    html = render(session)

    token = get_random_string(DELETE_TOKEN_LENGTH)
    paste = Paste(
        sha256=hashlib.sha256(redacted).hexdigest(),
        size_bytes=len(redacted),
        renderer_version=RENDERER_VERSION,
        adapter_version=ADAPTER_VERSION,
        uploader_ip=uploader_ip,
        harness=session.harness,
        session_model=session.model,
        turn_count=session.turn_count,
        tool_call_count=session.tool_call_count,
        delete_token_hash=hash_token(token),
    )

    storage = get_storage()
    storage.write_raw(paste.slug, redacted)
    storage.write_fragment(paste.slug, html)
    try:
        paste.save()
    except Exception:
        storage.delete(paste.slug)
        raise
    return paste, token


def delete_paste(paste: Paste) -> None:
    if paste.deleted_at is not None:
        return
    paste.deleted_at = timezone.now()
    paste.save(update_fields=["deleted_at"])
    get_storage().delete(paste.slug)
