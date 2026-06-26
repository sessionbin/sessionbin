from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "claude_code"
OPENCODE_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "opencode"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def opencode_fixtures_dir():
    return OPENCODE_FIXTURES_DIR
