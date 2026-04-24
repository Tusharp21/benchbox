from pathlib import Path

import pytest

from benchbox_core.detect import (
    OSInfo,
    UnsupportedOSError,
    detect_os,
    parse_os_release,
    require_supported,
)

UBUNTU_2404 = """\
PRETTY_NAME="Ubuntu 24.04 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
"""

DEBIAN_12 = """\
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
NAME="Debian GNU/Linux"
VERSION_ID="12"
VERSION_CODENAME=bookworm
ID=debian
"""


def test_parse_os_release_handles_quoted_and_unquoted() -> None:
    data = parse_os_release(UBUNTU_2404)
    assert data["ID"] == "ubuntu"
    assert data["VERSION_ID"] == "24.04"
    assert data["VERSION_CODENAME"] == "noble"
    assert data["PRETTY_NAME"] == "Ubuntu 24.04 LTS"


def test_parse_os_release_skips_blank_and_comments() -> None:
    assert parse_os_release("\n# comment\n\nID=ubuntu\n") == {"ID": "ubuntu"}


def test_parse_os_release_ignores_malformed_lines() -> None:
    assert parse_os_release("no-equals-sign\nID=ubuntu\n") == {"ID": "ubuntu"}


def test_detect_os_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "os-release"
    p.write_text(UBUNTU_2404)
    info = detect_os(p)
    assert info.distro == "ubuntu"
    assert info.version_id == "24.04"
    assert info.codename == "noble"
    assert info.pretty_name == "Ubuntu 24.04 LTS"


def test_detect_os_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedOSError):
        detect_os(tmp_path / "does-not-exist")


@pytest.mark.parametrize("version", ["22.04", "24.04"])
def test_require_supported_accepts_supported_ubuntu(version: str) -> None:
    info = OSInfo(
        distro="ubuntu",
        version_id=version,
        codename="noble",
        pretty_name=f"Ubuntu {version} LTS",
        arch="x86_64",
    )
    require_supported(info)


def test_require_supported_rejects_non_ubuntu() -> None:
    info = OSInfo(
        distro="debian",
        version_id="12",
        codename="bookworm",
        pretty_name="Debian 12",
        arch="x86_64",
    )
    with pytest.raises(UnsupportedOSError, match="Ubuntu only"):
        require_supported(info)


def test_require_supported_rejects_old_ubuntu() -> None:
    info = OSInfo(
        distro="ubuntu",
        version_id="20.04",
        codename="focal",
        pretty_name="Ubuntu 20.04 LTS",
        arch="x86_64",
    )
    with pytest.raises(UnsupportedOSError, match="20.04"):
        require_supported(info)


def test_require_supported_rejects_unknown_arch() -> None:
    info = OSInfo(
        distro="ubuntu",
        version_id="24.04",
        codename="noble",
        pretty_name="Ubuntu 24.04 LTS",
        arch="riscv64",
    )
    with pytest.raises(UnsupportedOSError, match="architecture"):
        require_supported(info)


def test_require_supported_accepts_aarch64() -> None:
    info = OSInfo(
        distro="ubuntu",
        version_id="24.04",
        codename="noble",
        pretty_name="Ubuntu 24.04 LTS",
        arch="aarch64",
    )
    require_supported(info)
