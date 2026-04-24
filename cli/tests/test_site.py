from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchbox_core import credentials
from benchbox_core.installer._run import CommandResult, CommandRunner
from typer.testing import CliRunner

from benchbox_cli.main import app


def _make_bench(path: Path) -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text("{}", encoding="utf-8")


def _make_site(bench: Path, name: str) -> None:
    site = bench / "sites" / name
    site.mkdir(parents=True, exist_ok=True)
    (site / "site_config.json").write_text(json.dumps({"db_name": f"_{name}"}), encoding="utf-8")
    (site / "apps.txt").write_text("frappe\n", encoding="utf-8")


def test_site_new_requires_stored_password_when_yes(cli: CliRunner, tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench(bench)

    result = cli.invoke(
        app,
        [
            "site",
            "new",
            str(bench),
            "s1.local",
            "--yes",
            "--admin-password",
            "a",
        ],
    )
    assert result.exit_code != 0


def test_site_new_with_saved_credentials(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = tmp_path / "bench"
    _make_bench(bench)
    credentials.set_mariadb_root_password("stored-pw")

    captured: list[tuple[tuple[str, ...], object]] = []

    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: object = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        captured.append((tuple(command), cwd))
        _make_site(bench, "s1.local")  # simulate bench's side effect
        return CommandResult(tuple(command), 0, "", "", True)

    monkeypatch.setattr(CommandRunner, "run", fake_run)

    result = cli.invoke(
        app,
        [
            "site",
            "new",
            str(bench),
            "s1.local",
            "--yes",
            "--admin-password",
            "admin-pw",
        ],
    )

    assert result.exit_code == 0, result.stderr
    argv, cwd = captured[0]
    assert argv[:3] == ("bench", "new-site", "s1.local")
    assert "--db-root-password" in argv
    assert argv[argv.index("--db-root-password") + 1] == "stored-pw"
    assert argv[argv.index("--admin-password") + 1] == "admin-pw"
    assert str(cwd) == str(bench)


def test_site_drop_rejects_missing_site(cli: CliRunner, tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench(bench)
    credentials.set_mariadb_root_password("pw")

    result = cli.invoke(app, ["site", "drop", str(bench), "ghost.local", "--yes"])
    assert result.exit_code == 2


def test_site_drop_happy_path(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = tmp_path / "bench"
    _make_bench(bench)
    _make_site(bench, "doomed.local")
    credentials.set_mariadb_root_password("pw")

    monkeypatch.setattr(
        CommandRunner,
        "run",
        lambda self, command, **kw: CommandResult(tuple(command), 0, "", "", True),
    )

    result = cli.invoke(app, ["site", "drop", str(bench), "doomed.local", "--yes"])
    assert result.exit_code == 0
    assert "dropped" in result.stdout
