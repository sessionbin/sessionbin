from click.testing import CliRunner

from sessionbin.cli import cli


def test_cli():
    result = CliRunner().invoke(cli)
    assert result.exit_code == 0
    assert result.output.strip() == "sessionbin"
