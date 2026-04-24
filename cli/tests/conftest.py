from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli() -> CliRunner:
    # Click 8.3+ always separates stderr from stdout; no constructor toggle.
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolated_benchbox_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the credentials store and log dir at tmp_path for every test.

    Prevents a test invocation from reading or writing the developer's real
    ``~/.benchbox/`` directory.
    """
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BENCHBOX_LOG_DIR", str(tmp_path / "logs"))
