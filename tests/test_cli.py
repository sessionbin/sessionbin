from __future__ import annotations

import time
from unittest.mock import patch

from click.testing import CliRunner

from sessionbin.api import APIError
from sessionbin.cli import _human_size, _time_ago, cli


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(42) == "42 B"

    def test_kilobytes(self):
        assert _human_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert _human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert _human_size(3 * 1024**3) == "3.0 GB"


class TestTimeAgo:
    def test_just_now(self):
        assert _time_ago(time.time()) == "just now"

    def test_minutes(self):
        assert _time_ago(time.time() - 120) == "2m ago"

    def test_hours(self):
        assert _time_ago(time.time() - 7200) == "2h ago"

    def test_days(self):
        assert _time_ago(time.time() - 172800) == "2d ago"


class TestUploadCommand:
    def test_upload_file(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text("{}")

        with (
            patch("sessionbin.cli.resolve_server_url", return_value="https://example.com"),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
            patch("sessionbin.cli.session_save") as mock_save,
        ):
            mock_client_cls.return_value.upload.return_value = {
                "slug": "abc123",
                "url": "https://example.com/p/abc123/",
                "delete_token": "tok-secret",
            }
            result = CliRunner().invoke(cli, ["upload", str(f)])

        assert result.exit_code == 0
        assert "abc123" in result.output
        mock_save.assert_called_once()
        saved_slug, saved_entry = mock_save.call_args[0]
        assert saved_slug == "abc123"
        assert saved_entry["delete_token"] == "tok-secret"

    def test_upload_too_large(self, tmp_path):
        f = tmp_path / "big.jsonl"
        f.write_bytes(b"x" * (10 * 1024 * 1024 + 1))

        result = CliRunner().invoke(cli, ["upload", str(f)])

        assert result.exit_code != 0
        assert "10 MB" in result.output

    def test_upload_api_error(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text("{}")

        with (
            patch("sessionbin.cli.resolve_server_url", return_value="https://example.com"),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
        ):
            mock_client_cls.return_value.upload.side_effect = APIError(413, "too large")
            result = CliRunner().invoke(cli, ["upload", str(f)])

        assert result.exit_code != 0
        assert "too large" in result.output

    def test_upload_latest_no_sessions(self):
        with patch("sessionbin.cli.most_recent", return_value=None):
            result = CliRunner().invoke(cli, ["upload", "--latest"])

        assert result.exit_code != 0
        assert "No sessions found" in result.output

    def test_upload_latest_declined(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text("{}")

        from sessionbin.detect import SessionInfo

        info = SessionInfo(
            path=f, mtime=f.stat().st_mtime, project="proj", title=None, summary=None
        )

        with patch("sessionbin.cli.most_recent", return_value=info):
            result = CliRunner().invoke(cli, ["upload", "--latest"], input="n\n")

        assert result.exit_code == 0
        assert "Upload?" in result.output

    def test_upload_latest_with_yes_flag(self, tmp_path):
        f = tmp_path / "session.jsonl"
        f.write_text("{}")

        from sessionbin.detect import SessionInfo

        info = SessionInfo(
            path=f, mtime=f.stat().st_mtime, project="proj", title=None, summary=None
        )

        with (
            patch("sessionbin.cli.most_recent", return_value=info),
            patch("sessionbin.cli.resolve_server_url", return_value="https://example.com"),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
            patch("sessionbin.cli.session_save"),
        ):
            mock_client_cls.return_value.upload.return_value = {
                "slug": "s1",
                "url": "https://example.com/p/s1/",
                "delete_token": "tok",
            }
            result = CliRunner().invoke(cli, ["upload", "--latest", "-y"])

        assert result.exit_code == 0
        assert "Uploaded" in result.output


class TestListCommand:
    def test_list_empty(self):
        with patch("sessionbin.cli.sessions_all", return_value=[]):
            result = CliRunner().invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "No uploads tracked" in result.output

    def test_list_with_entries(self):
        entries = [
            {
                "slug": "abc123",
                "server": "https://example.com",
                "filename": "session.jsonl",
                "uploaded_at": "2025-01-01T00:00:00Z",
                "url": "https://example.com/p/abc123/",
            },
        ]
        with patch("sessionbin.cli.sessions_all", return_value=entries):
            result = CliRunner().invoke(cli, ["list"])

        assert result.exit_code == 0
        assert "https://example.com/p/abc123/" in result.output
        assert "session.jsonl" in result.output
        assert "2025-01-01T00:00:00Z" in result.output


class TestDeleteCommand:
    def test_delete_success(self):
        entry = {"delete_token": "tok", "server": "https://example.com"}

        with (
            patch("sessionbin.cli.session_get", return_value=entry),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
            patch("sessionbin.cli.session_remove") as mock_remove,
        ):
            mock_client_cls.return_value.delete.return_value = None
            result = CliRunner().invoke(cli, ["delete", "abc123"])

        assert result.exit_code == 0
        assert "Deleted abc123" in result.output
        mock_remove.assert_called_once_with("abc123")

    def test_delete_no_local_record(self):
        with patch("sessionbin.cli.session_get", return_value=None):
            result = CliRunner().invoke(cli, ["delete", "abc123"])

        assert result.exit_code != 0
        assert "No local record" in result.output

    def test_delete_api_error(self):
        entry = {"delete_token": "tok", "server": "https://example.com"}

        with (
            patch("sessionbin.cli.session_get", return_value=entry),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
        ):
            mock_client_cls.return_value.delete.side_effect = APIError(404, "not found")
            result = CliRunner().invoke(cli, ["delete", "abc123"])

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_delete_with_server_flag(self):
        entry = {"delete_token": "tok", "server": "https://old.example.com"}

        with (
            patch("sessionbin.cli.session_get", return_value=entry),
            patch("sessionbin.cli.SessionbinClient") as mock_client_cls,
            patch("sessionbin.cli.session_remove"),
        ):
            mock_client_cls.return_value.delete.return_value = None
            result = CliRunner().invoke(
                cli, ["delete", "abc123", "--server", "https://new.example.com"]
            )

        assert result.exit_code == 0
        mock_client_cls.assert_called_once_with("https://new.example.com")
