import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from benchbox_core import preflight
from benchbox_core.preflight import (
    CheckResult,
    PreflightReport,
    _port_in_use,
    check_disk,
    check_internet,
    check_port,
    check_ram,
    check_sudo,
    run_preflight,
)


def test_check_ram_passes_below_available() -> None:
    result = check_ram(min_gb=0.001)
    assert result.passed
    assert result.name == "ram"


def test_check_ram_fails_above_available() -> None:
    result = check_ram(min_gb=10**9)
    assert not result.passed


def test_check_disk_passes_on_existing_path(tmp_path: Path) -> None:
    result = check_disk(tmp_path, min_free_gb=0.001)
    assert result.passed


def test_check_disk_fails_with_huge_requirement(tmp_path: Path) -> None:
    result = check_disk(tmp_path, min_free_gb=10**9)
    assert not result.passed


@pytest.fixture
def bound_port() -> Iterator[int]:
    """A TCP port currently bound by this process."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_port_in_use_true_when_bound(bound_port: int) -> None:
    assert _port_in_use(bound_port) is True


def test_port_in_use_false_for_likely_free_port() -> None:
    # Pick a port at random by binding to 0, close it, then check. There's a
    # theoretical race but in practice this is stable.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert _port_in_use(port) is False


def test_check_port_result_shape(bound_port: int) -> None:
    result = check_port(bound_port)
    assert result.name == f"port:{bound_port}"
    assert result.passed is False
    assert "in use" in result.message


def test_check_port_with_expected_service_active(
    bound_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Port in use + the named service is ``active`` → pass with "expected" message.
    from benchbox_core.stats import ServiceStatus

    monkeypatch.setattr(
        "benchbox_core.stats.get_service_status",
        lambda name: ServiceStatus(name=name, active=True, state="active"),
    )
    result = check_port(bound_port, expected_service="mariadb")
    assert result.passed is True
    assert "mariadb" in result.message
    assert "expected" in result.message


def test_check_port_with_expected_service_inactive(
    bound_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Port in use BUT the named service is inactive → fail, with a message
    # that makes the mismatch obvious.
    from benchbox_core.stats import ServiceStatus

    monkeypatch.setattr(
        "benchbox_core.stats.get_service_status",
        lambda name: ServiceStatus(name=name, active=False, state="inactive"),
    )
    result = check_port(bound_port, expected_service="mariadb")
    assert result.passed is False
    assert "inactive" in result.message


def test_check_port_free_ignores_expected_service(monkeypatch: pytest.MonkeyPatch) -> None:
    # Don't bother asking systemctl if the port is already free.
    calls: list[str] = []

    def spy(name: str) -> object:
        calls.append(name)
        raise AssertionError("should not be called for a free port")

    monkeypatch.setattr("benchbox_core.stats.get_service_status", spy)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    result = check_port(port, expected_service="mariadb")
    assert result.passed is True
    assert calls == []


def test_check_internet_success_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Fake:
        def __enter__(self) -> "_Fake":
            return self

        def __exit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(
        "benchbox_core.preflight.socket.create_connection",
        lambda *a, **kw: _Fake(),
    )
    result = check_internet()
    assert result.passed


def test_check_internet_failure_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **kw: object) -> None:
        raise OSError("network down")

    monkeypatch.setattr("benchbox_core.preflight.socket.create_connection", boom)
    result = check_internet()
    assert not result.passed
    assert "network down" in result.message


def test_check_sudo_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.preflight.shutil.which", lambda _n: "/usr/bin/sudo")
    result = check_sudo()
    assert result.passed


def test_check_sudo_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_core.preflight.shutil.which", lambda _n: None)
    result = check_sudo()
    assert not result.passed


def test_preflight_report_overall_passed() -> None:
    report = PreflightReport(
        checks=[
            CheckResult("a", True, "ok"),
            CheckResult("b", True, "ok"),
        ]
    )
    assert report.passed is True
    assert report.failures == []


def test_preflight_report_overall_failed() -> None:
    failing = CheckResult("b", False, "nope")
    report = PreflightReport(
        checks=[
            CheckResult("a", True, "ok"),
            failing,
        ]
    )
    assert report.passed is False
    assert report.failures == [failing]


def test_run_preflight_smokes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Skip network to avoid any flakiness.
    monkeypatch.setattr(
        "benchbox_core.preflight.shutil.which",
        lambda _n: "/usr/bin/sudo",
    )
    report = run_preflight(
        min_ram_gb=0.001,
        min_free_disk_gb=0.001,
        ports=(0,),  # port 0 is special — ignored by _port_in_use on most systems
        disk_path=tmp_path,
        network=False,
    )
    # Names should at least include ram, disk, sudo.
    names = {c.name for c in report.checks}
    assert {"ram", "disk", "sudo"} <= names


def test_run_preflight_network_toggle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "benchbox_core.preflight.shutil.which",
        lambda _n: "/usr/bin/sudo",
    )
    report_no_net = run_preflight(
        min_ram_gb=0.001,
        min_free_disk_gb=0.001,
        ports=(),
        disk_path=tmp_path,
        network=False,
    )
    assert not any(c.name == "internet" for c in report_no_net.checks)

    monkeypatch.setattr(
        "benchbox_core.preflight.check_internet",
        lambda *a, **kw: CheckResult("internet", True, "mock"),
    )
    # Re-import run_preflight's reference via the module
    report_with_net = preflight.run_preflight(
        min_ram_gb=0.001,
        min_free_disk_gb=0.001,
        ports=(),
        disk_path=tmp_path,
        network=True,
    )
    assert any(c.name == "internet" for c in report_with_net.checks)
