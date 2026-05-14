"""Package data: QSS stylesheets + SVG icons.

Kept here (not in a top-level ``assets/`` dir) so hatch-pip ships them
inside the wheel and we can reach them via :mod:`importlib.resources`
regardless of where the package ended up on disk.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Literal

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

Theme = Literal["dark", "light"]
Accent = Literal["purple", "blue", "green", "orange", "pink", "red"]

# Default icon tint per theme. Overridable per-call via the ``color`` kwarg
# on :func:`icon`.
_ICON_TINT: dict[Theme, str] = {
    "dark": "#a9a9c4",
    "light": "#656d76",
}

# Preset accent palette. The base color flows into every QSS rule via the
# ``{accent}`` token; ``{accent_hover}`` is derived as a brightness shift so
# we don't have to hand-pick a hover variant per accent × theme.
ACCENT_BASE: dict[Accent, dict[Theme, str]] = {
    "purple": {"dark": "#bd93f9", "light": "#8250df"},
    "blue":   {"dark": "#8be9fd", "light": "#0969da"},
    "green":  {"dark": "#50fa7b", "light": "#1a7f37"},
    "orange": {"dark": "#ffb86c", "light": "#bc4c00"},
    "pink":   {"dark": "#ff79c6", "light": "#bf3989"},
    "red":    {"dark": "#ff5555", "light": "#cf222e"},
}


def accent_color(accent: Accent, theme: Theme) -> str:
    return ACCENT_BASE[accent][theme]


def _accent_hover(accent: Accent, theme: Theme) -> str:
    base = QColor(ACCENT_BASE[accent][theme])
    # Dark theme bg is dark, so hover stands out by getting lighter; light
    # theme bg is bright, so hover stands out by getting darker.
    shifted = base.lighter(115) if theme == "dark" else base.darker(115)
    return shifted.name()


@lru_cache(maxsize=16)
def stylesheet(theme: Theme = "dark", accent: Accent = "purple") -> str:
    filename = "style.qss" if theme == "dark" else "style_light.qss"
    raw = files(__package__).joinpath(filename).read_text(encoding="utf-8")
    return raw.replace("{accent_hover}", _accent_hover(accent, theme)).replace(
        "{accent}", accent_color(accent, theme)
    )


def _icon_svg_bytes(name: str) -> bytes:
    return files(__package__).joinpath("icons").joinpath(f"{name}.svg").read_bytes()


@lru_cache(maxsize=64)
def icon_path(name: str) -> Path:
    # Some APIs (QIcon(str)) want a filesystem path; on an installed wheel
    # this resolves to the extracted on-disk copy.
    return Path(str(files(__package__).joinpath("icons").joinpath(f"{name}.svg")))


@lru_cache(maxsize=64)
def icon(name: str, *, color: str | None = None, theme: Theme = "dark", size: int = 20) -> QIcon:
    """Render an SVG icon with ``currentColor`` swapped to ``color``.

    If ``color`` is ``None``, the palette default for ``theme`` is used.
    """
    resolved = color if color is not None else _ICON_TINT[theme]
    svg = _icon_svg_bytes(name).decode("utf-8")
    # SVGs use stroke="currentColor" by default; Qt's SVG renderer doesn't
    # resolve currentColor, so we substitute inline.
    tinted = svg.replace("currentColor", resolved)
    renderer = QSvgRenderer(tinted.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    from PySide6.QtGui import QPainter

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
