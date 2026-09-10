"""A gitleaks failure must not become an unhandled 500.

RedactionError is raised for a timeout, a missing binary, or any unexpected exit code.
None of those are the uploader's fault and none should leak a stack trace.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from sessionbin.pastes.models import Paste
from sessionbin.pastes.views import SCAN_FAILED_MESSAGE
from sessionbin.security.redact import RedactionError


@pytest.fixture
def gitleaks_fails(monkeypatch):
    def boom(raw: bytes) -> bytes:
        raise RedactionError("gitleaks timed out")

    monkeypatch.setattr("sessionbin.pastes.services.redact_secrets", boom)


def as_upload(data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile("session.jsonl", data, content_type="application/jsonl")


@pytest.mark.django_db
class TestApiUpload:
    def test_returns_503_not_500(self, client, fixture_bytes, gitleaks_fails):
        resp = client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 503
        assert "error" in resp.json()

    def test_no_paste_is_recorded(self, client, fixture_bytes, gitleaks_fails):
        client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        assert Paste.objects.count() == 0

    def test_succeeds_normally_when_gitleaks_works(self, client, fixture_bytes):
        resp = client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 200


@pytest.mark.django_db
class TestFormUpload:
    def test_redisplays_the_form_with_an_error(self, client, fixture_bytes, gitleaks_fails):
        resp = client.post("/", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 200
        assert SCAN_FAILED_MESSAGE.encode() in resp.content

    def test_no_paste_is_recorded(self, client, fixture_bytes, gitleaks_fails):
        client.post("/", {"file": as_upload(fixture_bytes)})
        assert Paste.objects.count() == 0

    def test_redirects_normally_when_gitleaks_works(self, client, fixture_bytes):
        resp = client.post("/", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 302
        assert "/manage/?token=" in resp["Location"]
