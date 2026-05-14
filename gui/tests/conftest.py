from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

# Force headless Qt before any PySide6 import in test code.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_benchbox_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from reading or writing the developer's ~/.benchbox."""
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BENCHBOX_LOG_DIR", str(tmp_path / "logs"))


def await_initial_load(qtbot: Any, view: Any, timeout: int = 2000) -> None:
    """Spin Qt's event loop until the view's async load worker has settled.

    Views built with the BusyLabel + OperationWorker pattern (Sites, Apps,
    Databases, BenchListView) kick off their first refresh in ``__init__``.
    Tests need to wait for the worker to emit before asserting on rendered
    state.
    """
    worker_attr = "_load_worker"

    def settled() -> bool:
        worker = getattr(view, worker_attr, None)
        return worker is None or not worker.isRunning()

    qtbot.waitUntil(settled, timeout=timeout)
    # Let the queued succeeded/failed slot drain on the main thread before
    # the caller asserts.
    qtbot.wait(0)
