import pytest

from sessionbin.storage.factory import get_storage


@pytest.fixture
def fixture_bytes(fixtures_dir):
    path = fixtures_dir / "3ad58276-e4e5-44fb-87ee-5bfc3ac716dd.jsonl"
    return path.read_bytes()


@pytest.fixture(autouse=True)
def _storage_dir(tmp_path, settings):
    get_storage.cache_clear()
    settings.SESSIONBIN = {**settings.SESSIONBIN, "DATA_DIR": tmp_path}
