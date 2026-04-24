"""Non-secret local preferences — theme choice, saved defaults.

Sibling to :mod:`benchbox_core.credentials` but a separate file because
preferences aren't secrets: the credentials store stays at 0600 so nobody
reads it accidentally; ``preferences.json`` is plain user-readable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from benchbox_core.credentials import ENV_CONFIG_DIR, config_dir

_PREFERENCES_FILENAME: str = "preferences.json"

Theme = Literal["dark", "light"]
DEFAULT_THEME: Theme = "dark"


def preferences_path() -> Path:
    # Respect the same env var credentials uses so tests (and per-user
    # overrides) end up with one consistent config dir.
    return config_dir() / _PREFERENCES_FILENAME


def _load() -> dict[str, object]:
    path = preferences_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return dict(raw)


def _save(data: dict[str, object]) -> None:
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def get_theme() -> Theme:
    """Return the saved theme or :data:`DEFAULT_THEME` if unset / unknown."""
    stored = _load().get("theme")
    if stored == "dark":
        return "dark"
    if stored == "light":
        return "light"
    return DEFAULT_THEME


def set_theme(theme: Theme) -> None:
    if theme not in ("dark", "light"):
        raise ValueError(f"unknown theme: {theme!r}")
    data = _load()
    data["theme"] = theme
    _save(data)


__all__ = [
    "DEFAULT_THEME",
    "ENV_CONFIG_DIR",
    "Theme",
    "get_theme",
    "preferences_path",
    "set_theme",
]
