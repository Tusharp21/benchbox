from __future__ import annotations

from pathlib import Path

import pytest

from benchbox_core import preferences


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))


def test_default_theme_when_unset() -> None:
    assert preferences.get_theme() == "dark"


def test_set_then_get_roundtrips_theme() -> None:
    preferences.set_theme("light")
    assert preferences.get_theme() == "light"
    preferences.set_theme("dark")
    assert preferences.get_theme() == "dark"


def test_set_theme_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        preferences.set_theme("sepia")  # type: ignore[arg-type]


def test_preferences_file_stays_valid_json(tmp_path: Path) -> None:
    preferences.set_theme("light")
    import json

    raw = json.loads(preferences.preferences_path().read_text(encoding="utf-8"))
    assert raw == {"theme": "light"}


def test_preferences_does_not_touch_credentials(tmp_path: Path) -> None:
    # Preferences and credentials share the config dir but not the file —
    # touching one must not affect the other.
    from benchbox_core import credentials

    credentials.set_mariadb_root_password("secret")
    preferences.set_theme("light")

    assert credentials.get_mariadb_root_password() == "secret"
    assert preferences.get_theme() == "light"


def test_malformed_preferences_file_falls_back_to_default(tmp_path: Path) -> None:
    path = preferences.preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert preferences.get_theme() == preferences.DEFAULT_THEME
