import subprocess
from pathlib import Path

import pytest

from benchbox_core.stats import (
    ServiceStatus,
    get_cpu_percent,
    get_disk,
    get_memory,
    get_service_status,
    snapshot,
)


def test_get_memory_sane_values() -> None:
    mem = get_memory()
    assert mem.total_bytes > 0
    assert 0 <= mem.used_bytes <= mem.total_bytes
    assert 0.0 <= mem.percent <= 100.0


def test_get_disk_sane_values(tmp_path: Path) -> None:
    d = get_disk(tmp_path)
    assert d.total_bytes > 0
    assert 0 <= d.free_bytes <= d.total_bytes
    assert 0.0 <= d.percent <= 100.0
    assert d.path == tmp_path


def test_get_disk_defaults_to_home() -> None:
    d = get_disk()
    assert d.path == Path.home()


def test_get_cpu_percent_returns_float() -> None:
    # Non-blocking first call may return 0.0 — that's fine, just assert type.
    result = get_cpu_percent(interval=None)
    assert isinstance(result, float)
    assert 0.0 <= result <= 100.0


def test_get_service_status_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.stats.shutil.which", lambda _n: "/usr/bin/systemctl")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="active\n", stderr="")

    monkeypatch.setattr("benchbox_core.stats.subprocess.run", fake_run)
    s = get_service_status("mariadb")
    assert s == ServiceStatus(name="mariadb", active=True, state="active")


def test_get_service_status_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.stats.shutil.which", lambda _n: "/usr/bin/systemctl")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0], returncode=3, stdout="inactive\n", stderr=""
        )

    monkeypatch.setattr("benchbox_core.stats.subprocess.run", fake_run)
    s = get_service_status("redis-server")
    assert s.active is False
    assert s.state == "inactive"


def test_get_service_status_no_systemctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.stats.shutil.which", lambda _n: None)
    s = get_service_status("mariadb")
    assert s.active is False
    assert s.state == "unknown"


def test_get_service_status_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.stats.shutil.which", lambda _n: "/usr/bin/systemctl")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=1)

    monkeypatch.setattr("benchbox_core.stats.subprocess.run", fake_run)
    s = get_service_status("mariadb")
    assert s.state == "unknown"


def test_snapshot_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Short-circuit service lookups so the test doesn't depend on systemd.
    monkeypatch.setattr(
        "benchbox_core.stats.get_service_status",
        lambda name: ServiceStatus(name=name, active=True, state="active"),
    )
    snap = snapshot(cpu_interval=None, disk_path=tmp_path, services=("mariadb", "redis-server"))
    assert snap.memory.total_bytes > 0
    assert snap.disk.path == tmp_path
    assert [s.name for s in snap.services] == ["mariadb", "redis-server"]
    assert all(s.active for s in snap.services)
