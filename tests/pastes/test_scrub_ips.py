from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from sessionbin.pastes.management.commands.scrub_ips import IP_RETENTION_DAYS
from sessionbin.pastes.models import Paste


def make_paste(*, age_days: int, ip: str | None = "203.0.113.7", deleted: bool = False) -> Paste:
    paste = Paste.objects.create(
        delete_token_hash="x" * 64,
        sha256="a" * 64,
        size_bytes=1,
        renderer_version=1,
        adapter_version=1,
        uploader_ip=ip,
        deleted_at=timezone.now() if deleted else None,
    )
    # created_at is auto_now_add, so it has to be rewritten with a queryset update.
    Paste.objects.filter(pk=paste.pk).update(created_at=timezone.now() - timedelta(days=age_days))
    paste.refresh_from_db()
    return paste


def scrub(*args) -> str:
    out = StringIO()
    call_command("scrub_ips", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestScrubIps:
    def test_clears_addresses_past_the_window(self):
        paste = make_paste(age_days=IP_RETENTION_DAYS + 1)
        scrub()
        paste.refresh_from_db()
        assert paste.uploader_ip is None

    def test_keeps_addresses_inside_the_window(self):
        paste = make_paste(age_days=IP_RETENTION_DAYS - 1)
        scrub()
        paste.refresh_from_db()
        assert paste.uploader_ip == "203.0.113.7"

    def test_the_boundary_errs_towards_scrubbing(self):
        # The window is a ceiling on retention, so a row at exactly the boundary goes.
        paste = make_paste(age_days=IP_RETENTION_DAYS)
        scrub()
        paste.refresh_from_db()
        assert paste.uploader_ip is None

    def test_soft_deleted_pastes_are_scrubbed_too(self):
        paste = make_paste(age_days=IP_RETENTION_DAYS + 1, deleted=True)
        scrub()
        paste.refresh_from_db()
        assert paste.uploader_ip is None

    def test_already_null_rows_are_not_counted(self):
        make_paste(age_days=IP_RETENTION_DAYS + 1, ip=None)
        assert "Scrubbed 0 of 1" in scrub()

    def test_is_idempotent(self):
        make_paste(age_days=IP_RETENTION_DAYS + 1)
        assert "Scrubbed 1 of 1" in scrub()
        assert "Scrubbed 0 of 1" in scrub()

    def test_nothing_else_on_the_row_changes(self):
        paste = make_paste(age_days=IP_RETENTION_DAYS + 1)
        before = (paste.slug, paste.sha256, paste.created_at, paste.delete_token_hash)
        scrub()
        paste.refresh_from_db()
        assert (paste.slug, paste.sha256, paste.created_at, paste.delete_token_hash) == before

    def test_dry_run_reports_without_writing(self):
        paste = make_paste(age_days=IP_RETENTION_DAYS + 1)
        assert "Would scrub 1 of 1" in scrub("--dry-run")
        paste.refresh_from_db()
        assert paste.uploader_ip == "203.0.113.7"
