import pytest

from sessionbin.storage.factory import get_storage


@pytest.fixture
def fixture_bytes(fixtures_dir):
    path = fixtures_dir / "f9e8d7c6-b5a4-3210-fedc-ba9876543210.jsonl"
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _storage_dir(tmp_path, settings):
    get_storage.cache_clear()
    settings.SESSIONBIN = {**settings.SESSIONBIN, "DATA_DIR": tmp_path}
