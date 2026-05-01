import subprocess
from unittest.mock import patch

import pytest

from sessionbin.security.redact import RedactionError, redact_secrets

SLACK_TOKEN = b"xoxb-1234567890-1234567890123-ABCDEFGHIJKLMNOPqrstuvwx"
OPENAI_KEY = (
    b"sk-proj-1234567890abcdefABCDEFghijklmn"
    b"1234567890abcdefABCDEFghijklmn"
    b"1234567890abcdefABCDEFghijklmn"
    b"1234567890abcdefABCDEFghijklmn"
    b"1234567890abcdefA"
)


class TestRedactSecrets:
    def test_clean_input_unchanged(self):
        raw = b"no secrets here, just normal text\n"
        assert redact_secrets(raw) == raw

    def test_single_secret_redacted(self):
        raw = b'SLACK_TOKEN = "' + SLACK_TOKEN + b'"'
        result = redact_secrets(raw)
        assert SLACK_TOKEN not in result
        assert b"<REDACTED>" in result

    def test_multiple_different_secrets(self):
        raw = b"token1: " + SLACK_TOKEN + b"\ntoken2: " + OPENAI_KEY + b"\n"
        result = redact_secrets(raw)
        assert SLACK_TOKEN not in result
        assert OPENAI_KEY not in result
        assert result.count(b"<REDACTED>") >= 2

    def test_duplicate_secret_both_redacted(self):
        raw = b"first: " + SLACK_TOKEN + b"\nsecond: " + SLACK_TOKEN + b"\n"
        result = redact_secrets(raw)
        assert SLACK_TOKEN not in result
        assert result.count(b"<REDACTED>") == 2

    def test_surrounding_text_preserved(self):
        raw = b"before " + SLACK_TOKEN + b" after"
        result = redact_secrets(raw)
        assert result == b"before <REDACTED> after"

    def test_timeout_raises_redaction_error(self):
        with patch("sessionbin.security.redact.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="gitleaks", timeout=30)
            with pytest.raises(RedactionError, match="timed out"):
                redact_secrets(b"test")

    def test_missing_gitleaks_raises_redaction_error(self):
        with patch("sessionbin.security.redact.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gitleaks")
            with pytest.raises(RedactionError, match="not installed"):
                redact_secrets(b"test")

    def test_unexpected_exit_code_raises_redaction_error(self):
        with patch("sessionbin.security.redact.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 2
            mock_run.return_value.stderr = b"some error"
            with pytest.raises(RedactionError, match="exited with code 2"):
                redact_secrets(b"test")
