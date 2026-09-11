"""Upload throttling, against the configured rate rather than an overridden one."""

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from sessionbin.pastes.models import Paste
from sessionbin.pastes.views import RATE_LIMITED_MESSAGE, upload_throttle

RATE = int(settings.SESSIONBIN["UPLOAD_RATE"].split("/")[0])


def as_upload(data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile("session.jsonl", data, content_type="application/jsonl")


@pytest.mark.django_db
class TestApiThrottle:
    def test_allows_up_to_the_limit_then_returns_429(self, client, fixture_bytes):
        for i in range(RATE):
            resp = client.post("/api/upload", {"file": as_upload(fixture_bytes)})
            assert resp.status_code == 200, f"request {i + 1} of {RATE} should have been allowed"
        resp = client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 429

    def test_a_throttled_upload_stores_nothing(self, client, fixture_bytes):
        for _ in range(RATE + 1):
            client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        assert Paste.objects.count() == RATE

    def test_a_different_address_has_its_own_budget(self, client, fixture_bytes):
        for _ in range(RATE + 1):
            client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        resp = client.post(
            "/api/upload", {"file": as_upload(fixture_bytes)}, REMOTE_ADDR="198.51.100.4"
        )
        assert resp.status_code == 200


@pytest.mark.django_db
class TestFormThrottle:
    def test_shows_a_message_and_returns_429(self, client, fixture_bytes):
        for _ in range(RATE):
            client.post("/", {"file": as_upload(fixture_bytes)})
        resp = client.post("/", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 429
        assert RATE_LIMITED_MESSAGE.encode() in resp.content

    def test_counters_are_shared_with_the_api(self, client, fixture_bytes):
        for _ in range(RATE):
            client.post("/api/upload", {"file": as_upload(fixture_bytes)})
        resp = client.post("/", {"file": as_upload(fixture_bytes)})
        assert resp.status_code == 429


class TestThrottleIdentity:
    def test_a_spoofed_forwarded_prefix_cannot_win_a_fresh_bucket(self):
        class Request:
            def __init__(self, xff):
                self.META = {"HTTP_X_FORWARDED_FOR": xff, "REMOTE_ADDR": "203.0.113.7"}

        idents = {
            upload_throttle.get_ident(Request(f"{n}.{n}.{n}.{n}, 203.0.113.7")) for n in (7, 8, 9)
        }
        assert idents == {"203.0.113.7"}
