from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force headless Qt before any PySide6 import in test code.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_benchbox_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading or writing the developer's ~/.benchbox."""
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BENCHBOX_LOG_DIR", str(tmp_path / "logs"))
