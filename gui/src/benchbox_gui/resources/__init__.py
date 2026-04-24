"""Package data: QSS stylesheet + SVG icons.

Kept here (not in a top-level ``assets/`` dir) so hatch-pip ships them
inside the wheel and we can reach them via :mod:`importlib.resources`
regardless of where the package ended up on disk.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer


@lru_cache(maxsize=1)
def stylesheet() -> str:
    return files(__package__).joinpath("style.qss").read_text(encoding="utf-8")


def _icon_svg_bytes(name: str) -> bytes:
    return files(__package__).joinpath("icons").joinpath(f"{name}.svg").read_bytes()


@lru_cache(maxsize=64)
def icon_path(name: str) -> Path:
    # Some APIs (QIcon(str)) want a filesystem path; on an installed wheel
    # this resolves to the extracted on-disk copy.
    return Path(str(files(__package__).joinpath("icons").joinpath(f"{name}.svg")))


@lru_cache(maxsize=64)
def icon(name: str, *, color: str = "#a9a9c4", size: int = 20) -> QIcon:
    """Render an SVG icon with ``currentColor`` replaced by ``color``."""
    svg = _icon_svg_bytes(name).decode("utf-8")
    # SVGs use stroke="currentColor" by default; Qt's SVG renderer doesn't
    # resolve currentColor, so we substitute inline.
    tinted = svg.replace("currentColor", color)
    renderer = QSvgRenderer(tinted.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    from PySide6.QtGui import QPainter

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
