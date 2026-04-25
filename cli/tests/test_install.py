from __future__ import annotations

import pytest
from benchbox_core import credentials, detect
from typer.testing import CliRunner

from benchbox_cli.main import app


def _fake_ubuntu(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = detect.OSInfo(
        distro="ubuntu",
        version_id="22.04",
        codename="jammy",
        pretty_name="Ubuntu 22.04.3 LTS",
        arch="x86_64",
    )
    monkeypatch.setattr("benchbox_cli.install.detect.detect_os", lambda *a, **kw: fake)
    monkeypatch.setattr("benchbox_cli.install.detect.require_supported", lambda info: None)


def _pass_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    from benchbox_core.preflight import CheckResult, PreflightReport

    report = PreflightReport(checks=[CheckResult("ram", True, "ok")])
    monkeypatch.setattr("benchbox_cli.install.preflight.run_preflight", lambda: report)


def test_install_fails_on_unsupported_os(cli: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(info: object) -> None:
        raise detect.UnsupportedOSError("nope")

    monkeypatch.setattr(
        "benchbox_cli.install.detect.detect_os",
        lambda *a, **kw: detect.OSInfo("debian", "12", "bookworm", "Debian 12", "x86_64"),
    )
    monkeypatch.setattr("benchbox_cli.install.detect.require_supported", boom)

    result = cli.invoke(app, ["install"])
    assert result.exit_code == 2
    assert "unsupported host" in result.stderr


def test_install_requires_stored_password_when_yes(
    cli: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_ubuntu(monkeypatch)
    _pass_preflight(monkeypatch)
    # No credentials stored → --yes must bail with a clear message.
    result = cli.invoke(app, ["install", "--yes", "--dry-run"])
    assert result.exit_code != 0


def test_install_dry_run_prints_plans_without_executing(
    cli: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_ubuntu(monkeypatch)
    _pass_preflight(monkeypatch)
    credentials.set_mariadb_root_password("test-pw")

    # Neutralise every probe_runner so plan() doesn't shell out.
    from benchbox_core.installer._run import CommandResult, CommandRunner

    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: object = None,
        check: bool = False,
        timeout: float | None = None,
        line_callback: object | None = None,
    ) -> CommandResult:
        # Every probe returns "not installed / service inactive"
        return CommandResult(tuple(command), 1, "", "", True)

    monkeypatch.setattr(CommandRunner, "run", fake_run)

    result = cli.invoke(app, ["install", "--dry-run", "--yes"])
    assert result.exit_code == 0
    assert "dry-run" in result.stdout


def test_install_skip_preflight(cli: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ubuntu(monkeypatch)
    credentials.set_mariadb_root_password("test-pw")

    called = {"n": 0}

    def counted() -> object:
        called["n"] += 1
        from benchbox_core.preflight import PreflightReport

        return PreflightReport(checks=[])

    monkeypatch.setattr("benchbox_cli.install.preflight.run_preflight", counted)

    # No runner override needed for dry-run: components probe via their own
    # probe_runner default. Provide a neutral runner.
    from benchbox_core.installer._run import CommandResult, CommandRunner

    monkeypatch.setattr(
        CommandRunner,
        "run",
        lambda self, command, **kw: CommandResult(tuple(command), 1, "", "", True),
    )

    result = cli.invoke(app, ["install", "--dry-run", "--yes", "--skip-preflight"])
    assert result.exit_code == 0
    assert called["n"] == 0  # preflight skipped
