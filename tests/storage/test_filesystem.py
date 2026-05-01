import gzip

import pytest

from sessionbin.storage.exceptions import NotFoundError
from sessionbin.storage.filesystem import FilesystemStorage


@pytest.fixture
def storage(tmp_path):
    return FilesystemStorage(tmp_path)


class TestWriteRaw:
    def test_round_trip(self, storage, tmp_path):
        data = b'{"type":"user","message":"hello"}\n'
        storage.write_raw("abc123", data)
        on_disk = (tmp_path / "raw" / "abc123.jsonl.gz").read_bytes()
        assert gzip.decompress(on_disk) == data


class TestReadRaw:
    def test_round_trip(self, storage):
        data = b'{"type":"user","message":"hello"}\n'
        storage.write_raw("abc123", data)
        raw = storage.read_raw("abc123")
        assert gzip.decompress(raw) == data

    def test_missing_slug_raises_not_found(self, storage):
        with pytest.raises(NotFoundError):
            storage.read_raw("nosuchslug")


class TestWriteFragment:
    def test_round_trip(self, storage):
        html = "<div>transcript</div>"
        storage.write_fragment("abc123", html)
        assert storage.read_fragment("abc123") == html


class TestReadFragment:
    def test_missing_slug_raises_not_found(self, storage):
        with pytest.raises(NotFoundError):
            storage.read_fragment("nosuchslug")


class TestDelete:
    def test_removes_both_files(self, storage, tmp_path):
        storage.write_raw("abc123", b"data")
        storage.write_fragment("abc123", "html")
        storage.delete("abc123")
        assert not (tmp_path / "raw" / "abc123.jsonl.gz").exists()
        assert not (tmp_path / "fragments" / "abc123.html").exists()

    def test_nonexistent_slug_is_noop(self, storage):
        storage.delete("doesnotexist")

    def test_only_raw_present(self, storage, tmp_path):
        storage.write_raw("abc123", b"data")
        storage.delete("abc123")
        assert not (tmp_path / "raw" / "abc123.jsonl.gz").exists()

    def test_only_fragment_present(self, storage, tmp_path):
        storage.write_fragment("abc123", "html")
        storage.delete("abc123")
        assert not (tmp_path / "fragments" / "abc123.html").exists()


class TestSlugValidation:
    def test_path_traversal(self, storage):
        with pytest.raises(ValueError):
            storage.write_raw("../etc/passwd", b"")

    def test_slash_in_slug(self, storage):
        with pytest.raises(ValueError):
            storage.write_raw("a/b", b"")

    def test_too_long(self, storage):
        with pytest.raises(ValueError):
            storage.write_raw("a" * 33, b"")

    def test_uppercase_rejected(self, storage):
        with pytest.raises(ValueError):
            storage.write_raw("ABC", b"")

    def test_max_length_accepted(self, storage):
        storage.write_raw("a" * 32, b"ok")


class TestInit:
    def test_creates_subdirectories(self, tmp_path):
        data_dir = tmp_path / "new"
        FilesystemStorage(data_dir)
        assert (data_dir / "raw").is_dir()
        assert (data_dir / "fragments").is_dir()
