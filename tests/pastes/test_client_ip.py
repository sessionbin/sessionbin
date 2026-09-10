import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from sessionbin.conf.middleware import ClientIPMiddleware
from sessionbin.pastes.models import Paste


def remote_addr_after(meta):
    """REMOTE_ADDR as the view would see it, for a request carrying this META."""
    seen = {}

    def view(request):
        seen["addr"] = request.META.get("REMOTE_ADDR")
        return "response"

    class Request:
        pass

    request = Request()
    request.META = meta
    ClientIPMiddleware(view)(request)
    return seen["addr"]


class TestClientIPMiddleware:
    def test_no_header_leaves_remote_addr_alone(self):
        assert remote_addr_after({"REMOTE_ADDR": "127.0.0.1"}) == "127.0.0.1"

    def test_empty_header_leaves_remote_addr_alone(self):
        meta = {"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": ""}
        assert remote_addr_after(meta) == "127.0.0.1"

    def test_single_entry_is_used(self):
        meta = {"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": "203.0.113.7"}
        assert remote_addr_after(meta) == "203.0.113.7"

    def test_last_entry_wins_over_a_spoofed_prefix(self):
        # A client sending its own X-Forwarded-For gets its value kept as the prefix; the
        # proxy appends the address it actually saw. Trusting the first entry would let the
        # client pick any address it liked.
        meta = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8, 203.0.113.7",
        }
        assert remote_addr_after(meta) == "203.0.113.7"

    def test_whitespace_is_stripped(self):
        meta = {"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": "1.2.3.4,   203.0.113.7  "}
        assert remote_addr_after(meta) == "203.0.113.7"

    def test_ipv6_entry(self):
        meta = {"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": "1.2.3.4, 2001:db8::1"}
        assert remote_addr_after(meta) == "2001:db8::1"


@pytest.mark.django_db
class TestUploaderIPIsRecorded:
    """The middleware exists so uploader_ip stops being the proxy's address."""

    def test_api_upload_records_the_forwarded_client(self, client, fixture_bytes, settings):
        settings.MIDDLEWARE = [
            "sessionbin.conf.middleware.ClientIPMiddleware",
            *settings.MIDDLEWARE,
        ]
        upload = SimpleUploadedFile("s.jsonl", fixture_bytes, content_type="application/jsonl")
        resp = client.post(
            "/api/upload",
            {"file": upload},
            HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7",
        )
        assert resp.status_code == 200
        paste = Paste.objects.get(slug=resp.json()["slug"])
        assert paste.uploader_ip == "203.0.113.7"
