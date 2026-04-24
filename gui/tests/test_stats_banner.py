from __future__ import annotations

import pytest
from benchbox_core.stats import DiskStats, MemoryStats, ServiceStatus, SystemStats
from pytestqt.qtbot import QtBot

from benchbox_gui.views.stats_banner import StatsBanner


@pytest.fixture
def fake_snapshot(monkeypatch: pytest.MonkeyPatch) -> SystemStats:
    from pathlib import Path

    snap = SystemStats(
        cpu_percent=33.3,
        memory=MemoryStats(total_bytes=16 * 1024**3, used_bytes=4 * 1024**3, percent=25.0),
        disk=DiskStats(
            path=Path("/"), total_bytes=500 * 1024**3, free_bytes=250 * 1024**3, percent=50.0
        ),
        services=[
            ServiceStatus(name="mariadb", active=True, state="active"),
            ServiceStatus(name="redis-server", active=False, state="inactive"),
        ],
    )
    monkeypatch.setattr("benchbox_gui.views.stats_banner.stats.snapshot", lambda **kw: snap)
    return snap


def test_banner_emits_snapshot_on_refresh(qtbot: QtBot, fake_snapshot: SystemStats) -> None:
    # poll_ms large so only the manual refresh fires during the test.
    banner = StatsBanner(poll_ms=10_000)
    qtbot.addWidget(banner)

    with qtbot.waitSignal(banner.snapshot_ready, timeout=1000) as blocker:
        banner.refresh()
    assert blocker.args == [fake_snapshot]


def test_banner_labels_update_from_snapshot(qtbot: QtBot, fake_snapshot: SystemStats) -> None:
    from PySide6.QtWidgets import QLabel

    banner = StatsBanner(poll_ms=10_000)
    qtbot.addWidget(banner)
    banner.refresh()

    # Exact formatting isn't what we're testing; just that the snapshot
    # numbers and service names landed somewhere in the rendered labels.
    joined = "\n".join(lbl.text() for lbl in banner.findChildren(QLabel))
    assert "33.3" in joined
    assert "mariadb" in joined
    assert "redis-server" in joined
