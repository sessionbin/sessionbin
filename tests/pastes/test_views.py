import gzip

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from sessionbin.pastes.models import Paste
from sessionbin.pastes.services import create_paste_from_upload, delete_paste


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_returns_status_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "pastes" in data


@pytest.mark.django_db
class TestUploadEndpoint:
    def test_returns_slug_url_delete_token(self, client, fixture_bytes):
        resp = client.post("/api/upload", {"file": _as_upload(fixture_bytes)})
        assert resp.status_code == 200
        data = resp.json()
        assert "slug" in data
        assert "url" in data
        assert "delete_token" in data
        assert data["slug"] in data["url"]

    def test_file_too_large(self, client, settings):
        settings.SESSIONBIN = {**settings.SESSIONBIN, "MAX_UPLOAD_BYTES": 10}
        resp = client.post("/api/upload", {"file": _as_upload(b"x" * 11)})
        assert resp.status_code == 413
        data = resp.json()
        assert data["error"] == "file too large"
        assert data["max_bytes"] == 10


@pytest.mark.django_db
class TestViewPaste:
    def test_returns_200(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        assert resp.status_code == 200

    def test_contains_transcript(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        content = resp.content.decode()
        assert "sessionbin" in content
        assert paste.slug in content

    def test_contains_download_link(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        content = resp.content.decode()
        assert f"/raw/{paste.slug}.jsonl" in content
        assert "Download raw JSONL" in content

    def test_cache_control_header(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/")
        assert "max-age=86400" in resp["Cache-Control"]

    def test_nonexistent_slug_returns_404(self, client):
        resp = client.get("/p/nonexistent/")
        assert resp.status_code == 404

    def test_deleted_paste_returns_404(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        paste.deleted_at = timezone.now()
        paste.save()
        resp = client.get(f"/p/{paste.slug}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestRawPaste:
    def test_returns_200_with_correct_headers(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/raw/{paste.slug}.jsonl")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/jsonl"
        assert resp["Content-Encoding"] == "gzip"
        assert resp["Content-Disposition"] == f'attachment; filename="{paste.slug}.jsonl"'
        assert "max-age=86400" in resp["Cache-Control"]

    def test_content_matches_original(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/raw/{paste.slug}.jsonl")
        assert gzip.decompress(resp.content) == fixture_bytes

    def test_nonexistent_slug_returns_404(self, client):
        resp = client.get("/raw/nonexistent.jsonl")
        assert resp.status_code == 404

    def test_deleted_paste_returns_404(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        resp = client.get(f"/raw/{paste.slug}.jsonl")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestEndToEnd:
    def test_upload_then_view(self, client, fixture_bytes):
        upload_resp = client.post("/api/upload", {"file": _as_upload(fixture_bytes)})
        assert upload_resp.status_code == 200
        slug = upload_resp.json()["slug"]

        view_resp = client.get(f"/p/{slug}/")
        assert view_resp.status_code == 200
        assert slug in view_resp.content.decode()


@pytest.mark.django_db
class TestWebUpload:
    def test_get_returns_form(self, client):
        resp = client.get("/")
        content = resp.content.decode()
        assert resp.status_code == 200
        assert '<form method="post"' in content
        assert 'enctype="multipart/form-data"' in content

    def test_post_redirects_to_manage(self, client, fixture_bytes):
        resp = client.post("/", {"file": _as_upload(fixture_bytes)})
        assert resp.status_code == 302
        assert "/manage/" in resp["Location"]
        assert "token=" in resp["Location"]

    def test_post_redirect_token_works(self, client, fixture_bytes):
        resp = client.post("/", {"file": _as_upload(fixture_bytes)})
        manage_resp = client.get(resp["Location"])
        assert manage_resp.status_code == 200

    def test_post_without_file_returns_200_with_errors(self, client):
        resp = client.post("/", {})
        assert resp.status_code == 200
        assert Paste.objects.count() == 0

    def test_post_too_large_file(self, client, settings):
        settings.SESSIONBIN = {**settings.SESSIONBIN, "MAX_UPLOAD_BYTES": 10}
        resp = client.post("/", {"file": _as_upload(b"x" * 11)})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "too large" in content
        assert Paste.objects.count() == 0


@pytest.mark.django_db
class TestManagePaste:
    def test_get_with_valid_token(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/manage/?token={token}")
        assert resp.status_code == 200

    def test_get_without_token(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/manage/")
        assert resp.status_code == 404

    def test_get_with_wrong_token(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/manage/?token=wrong")
        assert resp.status_code == 404

    def test_get_nonexistent_slug(self, client):
        resp = client.get("/p/nonexistent/manage/?token=abc")
        assert resp.status_code == 404

    def test_shows_metadata_and_delete_button(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/manage/?token={token}")
        content = resp.content.decode()
        assert paste.slug in content
        assert f'href="{paste.url}"' in content
        assert "Delete this paste" in content

    def test_post_deletes_and_redirects(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        url = f"/p/{paste.slug}/manage/?token={token}"
        resp = client.post(url)
        assert resp.status_code == 302
        assert token in resp["Location"]
        paste.refresh_from_db()
        assert paste.deleted_at is not None

    def test_post_with_wrong_token(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.post(f"/p/{paste.slug}/manage/?token=wrong")
        assert resp.status_code == 404
        paste.refresh_from_db()
        assert paste.deleted_at is None

    def test_manage_page_after_deletion(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        resp = client.get(f"/p/{paste.slug}/manage/?token={token}")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "(deleted)" in content
        assert "Delete this paste" not in content
        assert f'href="{paste.url}"' not in content

    def test_post_on_already_deleted_is_noop(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        paste.refresh_from_db()
        first_deleted_at = paste.deleted_at
        url = f"/p/{paste.slug}/manage/?token={token}"
        resp = client.post(url)
        assert resp.status_code == 200
        paste.refresh_from_db()
        assert paste.deleted_at == first_deleted_at

    def test_referrer_meta_tag(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.get(f"/p/{paste.slug}/manage/?token={token}")
        assert "strict-origin-when-cross-origin" in resp.content.decode()


@pytest.mark.django_db
class TestApiDelete:
    def test_deletes_paste(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.delete(
            f"/api/p/{paste.slug}",
            headers={"X-Delete-Token": token},
        )
        assert resp.status_code == 204
        paste.refresh_from_db()
        assert paste.deleted_at is not None

    def test_wrong_token_returns_404(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        resp = client.delete(
            f"/api/p/{paste.slug}",
            headers={"X-Delete-Token": "wrong"},
        )
        assert resp.status_code == 404
        paste.refresh_from_db()
        assert paste.deleted_at is None

    def test_nonexistent_slug_returns_404(self, client):
        resp = client.delete(
            "/api/p/nonexistent",
            headers={"X-Delete-Token": "whatever"},
        )
        assert resp.status_code == 404

    def test_idempotent(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        headers = {"X-Delete-Token": token}
        resp1 = client.delete(f"/api/p/{paste.slug}", headers=headers)
        resp2 = client.delete(f"/api/p/{paste.slug}", headers=headers)
        assert resp1.status_code == 204
        assert resp2.status_code == 204

    def test_paste_view_404_after_delete(self, client, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        client.delete(
            f"/api/p/{paste.slug}",
            headers={"X-Delete-Token": token},
        )
        resp = client.get(f"/p/{paste.slug}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestEndToEndDelete:
    def test_web_upload_then_manage_then_delete(self, client, fixture_bytes):
        upload_resp = client.post("/", {"file": _as_upload(fixture_bytes)})
        manage_url = upload_resp["Location"]
        manage_resp = client.get(manage_url)
        assert manage_resp.status_code == 200
        assert "Delete this paste" in manage_resp.content.decode()

        delete_resp = client.post(manage_url)
        assert delete_resp.status_code == 302

        paste = Paste.objects.first()
        assert paste.deleted_at is not None
        assert client.get(f"/p/{paste.slug}/").status_code == 404

    def test_api_upload_then_api_delete(self, client, fixture_bytes):
        upload_resp = client.post("/api/upload", {"file": _as_upload(fixture_bytes)})
        data = upload_resp.json()
        assert client.get(f"/p/{data['slug']}/").status_code == 200

        delete_resp = client.delete(
            f"/api/p/{data['slug']}",
            headers={"X-Delete-Token": data["delete_token"]},
        )
        assert delete_resp.status_code == 204
        assert client.get(f"/p/{data['slug']}/").status_code == 404

    def test_api_upload_then_web_delete(self, client, fixture_bytes):
        upload_resp = client.post("/api/upload", {"file": _as_upload(fixture_bytes)})
        data = upload_resp.json()

        manage_url = f"/p/{data['slug']}/manage/?token={data['delete_token']}"
        client.post(manage_url)

        assert client.get(f"/p/{data['slug']}/").status_code == 404


def _as_upload(data: bytes, name: str = "session.jsonl"):
    return SimpleUploadedFile(name, data, content_type="application/octet-stream")
