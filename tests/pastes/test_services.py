import hashlib

import pytest

from sessionbin.adapters.claude_code import ADAPTER_VERSION
from sessionbin.pastes.models import Paste, hash_token
from sessionbin.pastes.render import RENDERER_VERSION
from sessionbin.pastes.services import create_paste_from_upload, delete_paste
from sessionbin.storage.exceptions import NotFoundError
from sessionbin.storage.factory import get_storage


@pytest.mark.django_db
class TestCreatePasteFromUpload:
    def test_sha256(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste.sha256 == hashlib.sha256(fixture_bytes).hexdigest()

    def test_size_bytes(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste.size_bytes == len(fixture_bytes)

    def test_versions(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste.renderer_version == RENDERER_VERSION
        assert paste.adapter_version == ADAPTER_VERSION

    def test_uploader_ip(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip="192.168.1.1")
        assert paste.uploader_ip == "192.168.1.1"

    def test_uploader_ip_none(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste.uploader_ip is None

    def test_slug_populated(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert len(paste.slug) == 10

    def test_delete_token_returned_and_hashed(self, fixture_bytes):
        paste, token = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert len(token) == 32
        assert paste.delete_token_hash == hash_token(token)

    def test_storage_files_written(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        storage = get_storage()
        fragment = storage.read_fragment(paste.slug)
        assert len(fragment) > 0

    def test_paste_persisted_to_db(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert Paste.objects.filter(slug=paste.slug).exists()

    def test_two_uploads_produce_different_slugs(self, fixture_bytes):
        paste1, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        paste2, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste1.slug != paste2.slug
        assert paste1.sha256 == paste2.sha256


@pytest.mark.django_db
class TestDeletePaste:
    def test_sets_deleted_at(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        assert paste.deleted_at is None
        delete_paste(paste)
        paste.refresh_from_db()
        assert paste.deleted_at is not None

    def test_removes_storage_files(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        storage = get_storage()
        assert len(storage.read_fragment(paste.slug)) > 0
        delete_paste(paste)
        with pytest.raises(NotFoundError):
            storage.read_fragment(paste.slug)

    def test_db_record_still_exists(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        assert Paste.objects.filter(slug=paste.slug).exists()

    def test_idempotent_on_already_deleted(self, fixture_bytes):
        paste, _ = create_paste_from_upload(raw=fixture_bytes, uploader_ip=None)
        delete_paste(paste)
        paste.refresh_from_db()
        first_deleted_at = paste.deleted_at
        delete_paste(paste)
        paste.refresh_from_db()
        assert paste.deleted_at == first_deleted_at
