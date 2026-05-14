"""Local preferences (theme, defaults)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from benchbox_core.credentials import ENV_CONFIG_DIR, config_dir

_PREFERENCES_FILENAME: str = "preferences.json"

Theme = Literal["dark", "light"]
DEFAULT_THEME: Theme = "dark"

# Accent is either one of the named presets below, or a free-form
# ``#rrggbb`` hex picked via the custom color dialog. Kept as ``str`` so
# both shapes round-trip through the same getter/setter.
Accent = str
DEFAULT_ACCENT: Accent = "purple"
_PRESET_ACCENTS: frozenset[str] = frozenset(
    ("purple", "blue", "green", "orange", "pink", "red")
)
_HEX_ACCENT_RE: re.Pattern[str] = re.compile(r"^#[0-9a-fA-F]{6}$")


def _is_valid_accent(value: object) -> bool:
    return isinstance(value, str) and (
        value in _PRESET_ACCENTS or bool(_HEX_ACCENT_RE.match(value))
    )


def is_custom_accent(value: str) -> bool:
    """True if ``value`` is a free-form hex color rather than a preset name."""
    return bool(_HEX_ACCENT_RE.match(value))


# Node major versions the installer can provision via nvm. v15 wants 18,
# v16 wants 24; the others bracket those for future Frappe bumps.
NodeMajor = Literal["18", "20", "22", "24"]
DEFAULT_NODE_MAJOR: NodeMajor = "18"
_VALID_NODE_MAJORS: frozenset[str] = frozenset(("18", "20", "22", "24"))


def preferences_path() -> Path:
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


def get_accent() -> Accent:
    stored = _load().get("accent")
    if _is_valid_accent(stored):
        return stored  # type: ignore[return-value]
    return DEFAULT_ACCENT


def set_accent(accent: Accent) -> None:
    if not _is_valid_accent(accent):
        raise ValueError(f"unknown accent: {accent!r}")
    data = _load()
    data["accent"] = accent
    _save(data)


def get_node_major() -> NodeMajor:
    stored = _load().get("node_major")
    if isinstance(stored, str) and stored in _VALID_NODE_MAJORS:
        return stored  # type: ignore[return-value]
    return DEFAULT_NODE_MAJOR


def set_node_major(major: NodeMajor) -> None:
    if major not in _VALID_NODE_MAJORS:
        raise ValueError(f"unknown node major: {major!r}")
    data = _load()
    data["node_major"] = major
    _save(data)


__all__ = [
    "Accent",
    "DEFAULT_ACCENT",
    "DEFAULT_NODE_MAJOR",
    "DEFAULT_THEME",
    "ENV_CONFIG_DIR",
    "NodeMajor",
    "Theme",
    "get_accent",
    "get_node_major",
    "get_theme",
    "is_custom_accent",
    "preferences_path",
    "set_accent",
    "set_node_major",
    "set_theme",
]
