"""Live system stats for the GUI top banner.

Cheap, snapshot-style reads — the GUI polls this on a timer (e.g. every
2 seconds) and redraws. Nothing here is authoritative for install decisions;
it's purely informational.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil

DEFAULT_SERVICES: tuple[str, ...] = ("mariadb", "redis-server")
SERVICE_QUERY_TIMEOUT_SEC: float = 3.0
NODE_QUERY_TIMEOUT_SEC: float = 3.0


@dataclass(frozen=True)
class MemoryStats:
    total_bytes: int
    used_bytes: int
    percent: float


@dataclass(frozen=True)
class DiskStats:
    path: Path
    total_bytes: int
    free_bytes: int
    percent: float


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    active: bool
    state: str  # "active", "inactive", "failed", "activating", "unknown", ...


@dataclass(frozen=True)
class SystemStats:
    cpu_percent: float
    memory: MemoryStats
    disk: DiskStats
    services: list[ServiceStatus]


def get_cpu_percent(interval: float | None = 0.1) -> float:
    """Return CPU usage as a percent. ``interval=None`` is non-blocking."""
    return float(psutil.cpu_percent(interval=interval))


def get_memory() -> MemoryStats:
    mem = psutil.virtual_memory()
    return MemoryStats(
        total_bytes=int(mem.total),
        used_bytes=int(mem.used),
        percent=float(mem.percent),
    )


def get_disk(path: Path | None = None) -> DiskStats:
    target = path or Path.home()
    usage = psutil.disk_usage(str(target))
    return DiskStats(
        path=target,
        total_bytes=int(usage.total),
        free_bytes=int(usage.free),
        percent=float(usage.percent),
    )


def get_service_status(name: str) -> ServiceStatus:
    """Query ``systemctl is-active <name>``.

    Returns ``state="unknown"`` on hosts without systemd or when the call
    times out — never raises.
    """
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return ServiceStatus(name=name, active=False, state="unknown")
    try:
        proc = subprocess.run(
            [systemctl, "is-active", name],
            capture_output=True,
            text=True,
            timeout=SERVICE_QUERY_TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return ServiceStatus(name=name, active=False, state="unknown")
    state = proc.stdout.strip() or "unknown"
    return ServiceStatus(name=name, active=(state == "active"), state=state)


def get_node_version() -> str | None:
    """Return the Node version Frappe will see, or ``None`` if no node is reachable.

    Frappe calls ``node`` from PATH after sourcing nvm; we mirror that
    lookup. Prefers the highest installed nvm-managed v18 (Frappe v15's
    required major), then the highest-major nvm install, then whatever
    apt-installed ``node`` is on PATH. Returns the bare version string
    without the leading ``v`` (e.g. ``"18.20.4"``).
    """
    nvm_versions = Path.home() / ".nvm" / "versions" / "node"
    if nvm_versions.is_dir():
        v18 = sorted(nvm_versions.glob("v18.*"), reverse=True)
        for candidate in v18 or sorted(nvm_versions.iterdir(), reverse=True):
            node_bin = candidate / "bin" / "node"
            if node_bin.is_file():
                version = _query_node_version(str(node_bin))
                if version is not None:
                    return version

    system_node = shutil.which("node")
    if system_node is not None:
        return _query_node_version(system_node)
    return None


def _query_node_version(node_bin: str) -> str | None:
    """Run ``<node_bin> --version`` and strip the leading ``v``."""
    try:
        proc = subprocess.run(
            [node_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=NODE_QUERY_TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    return raw.lstrip("v") or None


def snapshot(
    *,
    cpu_interval: float | None = 0.1,
    disk_path: Path | None = None,
    services: tuple[str, ...] = DEFAULT_SERVICES,
) -> SystemStats:
    """One-shot snapshot of every tracked stat."""
    return SystemStats(
        cpu_percent=get_cpu_percent(cpu_interval),
        memory=get_memory(),
        disk=get_disk(disk_path),
        services=[get_service_status(s) for s in services],
    )
