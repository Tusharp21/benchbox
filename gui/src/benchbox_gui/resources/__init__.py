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

# Default icon tint per theme. Overridable per-call via the ``color`` kwarg
# on :func:`icon`.
_ICON_TINT: dict[Theme, str] = {
    "dark": "#a9a9c4",
    "light": "#656d76",
}


@lru_cache(maxsize=2)
def stylesheet(theme: Theme = "dark") -> str:
    filename = "style.qss" if theme == "dark" else "style_light.qss"
    return files(__package__).joinpath(filename).read_text(encoding="utf-8")


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
