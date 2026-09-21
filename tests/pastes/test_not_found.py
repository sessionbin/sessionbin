import pytest
from django.contrib.staticfiles import finders

from sessionbin.pastes.services import create_paste_from_upload, delete_paste


@pytest.fixture(autouse=True)
def production_error_handling(settings):
    settings.DEBUG = False


def template_names(response):
    return [t.name for t in response.templates]


@pytest.mark.django_db
class TestCustomNotFoundPage:
    def test_unknown_slug(self, client):
        resp = client.get("/p/nosuchslug/")
        assert resp.status_code == 404
        assert "404.html" in template_names(resp)

    def test_unknown_url(self, client):
        resp = client.get("/no/such/page/")
        assert resp.status_code == 404
        assert "404.html" in template_names(resp)

    def test_deleted_paste(self, client, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        resp = client.get(f"/p/{paste.slug}/")
        assert resp.status_code == 404
        assert "404.html" in template_names(resp)

    def test_deleted_paste_is_indistinguishable_from_an_unknown_slug(self, client, fixture_bytes):
        """Saying which case it was would confirm the slug once held something."""
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        deleted = client.get(f"/p/{paste.slug}/").content
        unknown = client.get("/p/nosuchslug/").content
        assert deleted == unknown

    def test_carries_no_open_graph_metadata(self, client):
        body = client.get("/p/nosuchslug/").content.decode()
        assert "og:title" not in body
        assert "twitter:card" not in body

    def test_api_404_stays_json(self, client):
        resp = client.delete("/api/p/nosuchslug", headers={"x-delete-token": "nope"})
        assert resp.status_code == 404
        assert resp["Content-Type"].startswith("application/json")

    @pytest.mark.parametrize("path", ["/api/", "/api/bogus", "/api/deep/nested/path"])
    def test_unrouted_api_path_stays_json(self, client, path):
        """A path Ninja never registered fails in Django's resolver, not in Ninja."""
        resp = client.get(path)
        assert resp.status_code == 404
        assert resp["Content-Type"].startswith("application/json")
        assert resp.json() == {"detail": "Not Found"}

    def test_unrouted_api_path_matches_ninja_body(self, client):
        from_ninja = client.delete("/api/p/nosuchslug", headers={"x-delete-token": "nope"})
        from_resolver = client.get("/api/bogus")
        assert from_resolver.json() == from_ninja.json()


@pytest.mark.django_db
class TestApiStillRoutes:
    """The catch-all sits either side of the Ninja include, so prove it shadows nothing."""

    def test_docs_still_served(self, client):
        assert client.get("/api/docs").status_code == 200

    def test_openapi_schema_still_served(self, client):
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        assert resp.json()["openapi"]

    def test_health_still_served(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestFaviconAtRoot:
    def test_redirects_to_the_static_file(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 302
        assert resp["Location"] == "/static/favicon.ico"

    def test_the_file_it_points_at_exists(self):
        """A redirect to a renamed or deleted icon would be a 404 with extra steps."""
        assert finders.find("favicon.ico")
