from __future__ import annotations

from typer.testing import CliRunner

from benchbox_cli import __version__
from benchbox_cli.main import app


def test_help_exits_cleanly(cli: CliRunner) -> None:
    result = cli.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "benchbox" in result.stdout


def test_version_command_prints_version(cli: CliRunner) -> None:
    result = cli.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_all_subcommand_groups_registered(cli: CliRunner) -> None:
    result = cli.invoke(app, ["--help"])
    for group in ("install", "stats", "bench", "site", "app"):
        assert group in result.stdout


def test_no_args_shows_help(cli: CliRunner) -> None:
    result = cli.invoke(app, [])
    # no_args_is_help=True → exit code 2 with help printed
    assert result.exit_code == 2
    assert "benchbox" in result.stdout
