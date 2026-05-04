"""Pass/fail pill row for preflight checks."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_PASS_BG = "#1a7f37"
_FAIL_BG = "#cf222e"


def _make_pill(name: str, passed: bool, message: str) -> QLabel:
    glyph = "OK" if passed else "FAIL"
    bg = _PASS_BG if passed else _FAIL_BG
    label = QLabel(f"{glyph} · {name}")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setToolTip(message or "")
    label.setStyleSheet(
        f"background-color: {bg}; color: white; "
        "padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 10pt;"
    )
    return label


class PreflightStrip(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self._row.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(self._row)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_checks(self, checks: Iterable[object]) -> None:
        while self._row.count() > 1:
            item = self._row.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for check in checks:
            name = getattr(check, "name", "?")
            passed = bool(getattr(check, "passed", False))
            message = getattr(check, "message", "") or ""
            self._row.insertWidget(self._row.count() - 1, _make_pill(str(name), passed, str(message)))


__all__ = ["PreflightStrip"]
