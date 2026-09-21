import pytest
from django.core.management import call_command

from sessionbin.pastes.models import Paste
from sessionbin.pastes.render import RENDERER_VERSION
from sessionbin.pastes.services import create_paste_from_upload


@pytest.mark.django_db
def test_render_refreshes_paste_stats(fixture_bytes):
    paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
    Paste.objects.filter(slug=paste.slug).update(
        turn_count=999,
        tool_call_count=999,
        renderer_version=1,
        adapter_version=1,
        session_models=["stale-model"],
    )

    call_command("render", paste.slug)

    paste.refresh_from_db()
    assert paste.turn_count != 999
    assert paste.tool_call_count != 999
    assert paste.renderer_version == RENDERER_VERSION
    assert paste.adapter_version == 3
    assert paste.session_models == ["claude-sonnet-4-20250514"]
