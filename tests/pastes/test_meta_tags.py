import re

import pytest

from sessionbin.pastes.services import create_paste_from_upload, delete_paste


def _get_meta_content(html: str, attr: str, value: str) -> str | None:
    pattern = rf'<meta\s+{attr}="{re.escape(value)}"\s+content="([^"]*)"'
    m = re.search(pattern, html)
    if m:
        return m.group(1)
    pattern = rf'<meta\s+content="([^"]*)"\s+{attr}="{re.escape(value)}"'
    m = re.search(pattern, html)
    return m.group(1) if m else None


CORE_OG_TAGS = [
    ("property", "og:title"),
    ("property", "og:description"),
    ("property", "og:url"),
    ("property", "og:site_name"),
    ("property", "og:type"),
    ("name", "twitter:card"),
]


class TestLandingPageMeta:
    def test_has_core_tags(self, client):
        resp = client.get("/")
        html = resp.content.decode()
        for attr, name in CORE_OG_TAGS:
            content = _get_meta_content(html, attr, name)
            assert content is not None and content != "", f"Missing or empty: {name}"

    def test_twitter_tags_present(self, client):
        resp = client.get("/")
        html = resp.content.decode()
        for name in ("twitter:title", "twitter:description"):
            content = _get_meta_content(html, "name", name)
            assert content is not None and content != "", f"Missing or empty: {name}"


@pytest.mark.django_db
class TestPastePageMeta:
    def test_has_core_tags(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        for attr, name in CORE_OG_TAGS:
            content = _get_meta_content(html, attr, name)
            assert content is not None and content != "", f"Missing or empty: {name}"

    def test_og_url_matches_request(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        og_url = _get_meta_content(html, "property", "og:url")
        assert og_url is not None
        assert f"/p/{paste.slug}/" in og_url

    def test_description_contains_session_info(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        desc = _get_meta_content(html, "property", "og:description")
        assert desc is not None
        assert "session" in desc.lower()

    def test_title_contains_slug(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        title = _get_meta_content(html, "property", "og:title")
        assert title is not None
        assert paste.slug in title


@pytest.mark.django_db
class TestMetaEscaping:
    def test_html_in_content_is_escaped(self, client, fixture_bytes):
        # The fixture is a real JSONL; the harness/model fields are auto-escaped
        # by Django. Inject HTML-special chars via the model field directly.
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        paste.session_model = '<script>alert("xss")</script>'
        paste.save(update_fields=["session_model"])

        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        desc = _get_meta_content(html, "property", "og:description")
        assert desc is not None
        assert "<script>" not in desc
        assert "&lt;" in desc


@pytest.mark.django_db
class TestMetaTruncation:
    def test_description_max_250_chars(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        html = resp.content.decode()
        desc = _get_meta_content(html, "property", "og:description")
        assert desc is not None
        assert len(desc) <= 250


@pytest.mark.django_db
class TestDeletedPasteMeta:
    def test_deleted_paste_returns_404_no_meta(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        resp = client.get(f"/p/{paste.slug}/")
        assert resp.status_code == 404
        html = resp.content.decode()
        assert _get_meta_content(html, "property", "og:title") is None
