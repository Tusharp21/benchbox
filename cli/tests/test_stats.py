from __future__ import annotations

import pytest
from benchbox_core.stats import DiskStats, MemoryStats, ServiceStatus, SystemStats
from typer.testing import CliRunner

from benchbox_cli.main import app


def test_stats_command_renders(cli: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    fake = SystemStats(
        cpu_percent=12.5,
        memory=MemoryStats(total_bytes=16 * 1024**3, used_bytes=8 * 1024**3, percent=50.0),
        disk=DiskStats(
            path=Path("/"), total_bytes=500 * 1024**3, free_bytes=200 * 1024**3, percent=60.0
        ),
        services=[
            ServiceStatus(name="mariadb", active=True, state="active"),
            ServiceStatus(name="redis-server", active=False, state="inactive"),
        ],
    )
    monkeypatch.setattr("benchbox_cli.stats.stats.snapshot", lambda *a, **kw: fake)

    result = cli.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "12.5" in result.stdout
    assert "mariadb" in result.stdout
    assert "redis-server" in result.stdout


def test_stats_logs_subcommand_prints_path(cli: CliRunner) -> None:
    result = cli.invoke(app, ["stats", "logs"])
    assert result.exit_code == 0
    assert result.stdout.strip()  # some path was printed
