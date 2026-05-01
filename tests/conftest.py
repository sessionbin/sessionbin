from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "claude_code"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR
