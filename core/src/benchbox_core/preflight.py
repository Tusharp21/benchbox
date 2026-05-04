"""Preflight readiness checks."""

from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

import psutil

MIN_RAM_GB: float = 4.0
MIN_FREE_DISK_GB: float = 10.0
DEFAULT_PORTS: tuple[int, ...] = (3306, 6379, 8000)

# ``check_port`` will treat "port X in use" as a pass when the expected
# systemd service (value) for that port (key) is reporting active. Keeps
# the preflight honest BEFORE install (ports should be free) while not
# yelling AFTER install (MariaDB + Redis are correctly holding them).
EXPECTED_PORT_OWNER: dict[int, str] = {
    3306: "mariadb",
    6379: "redis-server",
}

INTERNET_HOST: str = "github.com"
INTERNET_PORT: int = 443
INTERNET_TIMEOUT_SEC: float = 3.0
_GB: int = 1024**3


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class PreflightReport:
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def check_ram(min_gb: float = MIN_RAM_GB) -> CheckResult:
    total_gb = psutil.virtual_memory().total / _GB
    passed = total_gb >= min_gb
    return CheckResult("ram", passed, f"{total_gb:.1f} GB total (need ≥ {min_gb} GB)")


def check_disk(path: Path | None = None, min_free_gb: float = MIN_FREE_DISK_GB) -> CheckResult:
    target = path or Path.home()
    try:
        usage = psutil.disk_usage(str(target))
    except OSError as err:
        return CheckResult("disk", False, f"could not read disk usage at {target}: {err}")
    free_gb = usage.free / _GB
    passed = free_gb >= min_free_gb
    return CheckResult(
        "disk",
        passed,
        f"{free_gb:.1f} GB free at {target} (need ≥ {min_free_gb} GB)",
    )


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def check_port(port: int, *, expected_service: str | None = None) -> CheckResult:
    in_use = _port_in_use(port)
    if not in_use:
        return CheckResult(f"port:{port}", True, f"port {port} is free")

    if expected_service is None:
        return CheckResult(f"port:{port}", False, f"port {port} is in use")

    # Import at call site to avoid pulling in stats.py (subprocess / psutil)
    # on bare preflight unless we actually need it.
    from benchbox_core.stats import get_service_status

    status = get_service_status(expected_service)
    if status.active:
        return CheckResult(
            f"port:{port}",
            True,
            f"port {port} is in use by {expected_service} (expected)",
        )

    return CheckResult(
        f"port:{port}",
        False,
        f"port {port} is in use (expected {expected_service}, but service is {status.state})",
    )


def check_internet(
    host: str = INTERNET_HOST,
    port: int = INTERNET_PORT,
    timeout: float = INTERNET_TIMEOUT_SEC,
) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as err:
        return CheckResult("internet", False, f"could not reach {host}:{port} ({err})")
    return CheckResult("internet", True, f"reached {host}:{port}")


def check_sudo() -> CheckResult:
    sudo = shutil.which("sudo")
    if sudo is None:
        return CheckResult("sudo", False, "sudo binary not found on PATH")
    return CheckResult("sudo", True, f"sudo found at {sudo}")


def run_preflight(
    *,
    min_ram_gb: float = MIN_RAM_GB,
    min_free_disk_gb: float = MIN_FREE_DISK_GB,
    ports: tuple[int, ...] = DEFAULT_PORTS,
    disk_path: Path | None = None,
    network: bool = True,
) -> PreflightReport:
    checks: list[CheckResult] = [
        check_ram(min_ram_gb),
        check_disk(disk_path, min_free_disk_gb),
    ]
    for p in ports:
        checks.append(check_port(p, expected_service=EXPECTED_PORT_OWNER.get(p)))
    if network:
        checks.append(check_internet())
    checks.append(check_sudo())
    return PreflightReport(checks=checks)
