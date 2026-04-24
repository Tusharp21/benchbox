"""OS detection and supported-version gate for benchbox.

benchbox v0.1 targets Ubuntu 22.04 and 24.04 only. Everything else should
fail loud, early, with a clear message — not silently try and produce a
half-working install.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_UBUNTU_VERSIONS: frozenset[str] = frozenset({"22.04", "24.04"})
SUPPORTED_ARCHS: frozenset[str] = frozenset({"x86_64", "aarch64"})


@dataclass(frozen=True)
class OSInfo:
    """Snapshot of the host OS relevant to benchbox's install decisions."""

    distro: str  # e.g. "ubuntu", "debian"
    version_id: str  # e.g. "24.04"
    codename: str  # e.g. "noble"
    pretty_name: str  # e.g. "Ubuntu 24.04 LTS"
    arch: str  # e.g. "x86_64"


class UnsupportedOSError(RuntimeError):
    """Host OS / version / architecture is outside benchbox's support matrix."""


def parse_os_release(content: str) -> dict[str, str]:
    """Parse the key=value format used by /etc/os-release.

    Values may be optionally wrapped in single or double quotes.
    """
    result: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def detect_os(os_release_path: Path = Path("/etc/os-release")) -> OSInfo:
    """Read /etc/os-release and return an OSInfo. Does not validate support."""
    if not os_release_path.exists():
        raise UnsupportedOSError(
            f"{os_release_path} not found — benchbox supports Linux hosts only"
        )
    data = parse_os_release(os_release_path.read_text())
    return OSInfo(
        distro=data.get("ID", "unknown"),
        version_id=data.get("VERSION_ID", ""),
        codename=data.get("VERSION_CODENAME", ""),
        pretty_name=data.get("PRETTY_NAME", data.get("NAME", "unknown")),
        arch=platform.machine(),
    )


def require_supported(info: OSInfo) -> None:
    """Raise UnsupportedOSError unless info is a supported Ubuntu/arch combo."""
    if info.distro != "ubuntu":
        raise UnsupportedOSError(
            f"benchbox v0.1 supports Ubuntu only (detected: {info.pretty_name or info.distro})"
        )
    if info.version_id not in SUPPORTED_UBUNTU_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_UBUNTU_VERSIONS))
        raise UnsupportedOSError(
            f"Ubuntu {info.version_id} is not supported — benchbox supports {supported}"
        )
    if info.arch not in SUPPORTED_ARCHS:
        raise UnsupportedOSError(f"Unsupported CPU architecture: {info.arch}")
