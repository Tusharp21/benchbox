from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from benchbox_core import credentials


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(credentials.ENV_CONFIG_DIR, str(tmp_path))


def test_get_returns_none_when_file_missing() -> None:
    assert credentials.get("mariadb_root_password") is None


def test_set_then_get_roundtrips(tmp_path: Path) -> None:
    credentials.set_("mariadb_root_password", "hunter2")
    assert credentials.get("mariadb_root_password") == "hunter2"
    assert (tmp_path / "credentials.json").is_file()


def test_set_creates_parent_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "deep" / "nested"
    monkeypatch.setenv(credentials.ENV_CONFIG_DIR, str(nested))
    credentials.set_("key", "value")
    assert (nested / "credentials.json").is_file()


def test_set_writes_0600_permissions(tmp_path: Path) -> None:
    credentials.set_("mariadb_root_password", "secret")
    mode = (tmp_path / "credentials.json").stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_set_preserves_0600_on_update(tmp_path: Path) -> None:
    credentials.set_("key", "v1")
    credentials.set_("key", "v2")
    mode = (tmp_path / "credentials.json").stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_set_does_not_clobber_other_keys() -> None:
    credentials.set_("a", "1")
    credentials.set_("b", "2")
    assert credentials.get("a") == "1"
    assert credentials.get("b") == "2"


def test_unset_removes_key() -> None:
    credentials.set_("a", "1")
    assert credentials.unset("a") is True
    assert credentials.get("a") is None


def test_unset_returns_false_when_missing() -> None:
    assert credentials.unset("nope") is False


def test_mariadb_helpers_roundtrip() -> None:
    assert credentials.get_mariadb_root_password() is None
    credentials.set_mariadb_root_password("p@ssw0rd")
    assert credentials.get_mariadb_root_password() == "p@ssw0rd"


def test_malformed_credentials_file_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text("{not json", encoding="utf-8")
    assert credentials.get("anything") is None


def test_non_dict_json_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert credentials.get("anything") is None


def test_env_override_changes_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(credentials.ENV_CONFIG_DIR, str(tmp_path / "override"))
    assert credentials.config_dir() == tmp_path / "override"
    assert credentials.credentials_path() == tmp_path / "override" / "credentials.json"


def test_set_rejects_world_readable_after_umask(tmp_path: Path) -> None:
    # Even with a permissive umask, saved file must end at 0600.
    old = os.umask(0o000)
    try:
        credentials.set_("key", "value")
        mode = (tmp_path / "credentials.json").stat().st_mode
        assert stat.S_IMODE(mode) == 0o600
    finally:
        os.umask(old)
