"""QThread workers for long-running core operations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from benchbox_core.installer import (
    CommandRunner,
    Component,
    ComponentPlan,
    ComponentResult,
    InstallResult,
)
from PySide6.QtCore import QThread, Signal


class OperationWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


class StreamingOpWorker(QThread):
    """Worker for ops that take a line_callback for live stdout/stderr."""

    line_received = Signal(str)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, operation: Callable[[Callable[[str], None]], Any]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation(self.line_received.emit)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


class InstallWorker(QThread):
    component_started = Signal(str, int, int)
    component_finished = Signal(str, bool)
    install_finished = Signal(object)

    def __init__(
        self,
        components: Sequence[Component],
        *,
        dry_run: bool = False,
    ) -> None:
        super().__init__()
        self._components = list(components)
        self._dry_run = dry_run

    def run(self) -> None:
        results: list[ComponentResult] = []
        runner = CommandRunner(dry_run=self._dry_run)
        total = len(self._components)

        for idx, component in enumerate(self._components):
            self.component_started.emit(component.name, idx, total)
            plan: ComponentPlan = component.plan()
            apply = getattr(component, "apply", None)
            if apply is None:
                results.append(ComponentResult(component=component.name, results=()))
                self.component_finished.emit(component.name, False)
                break
            result: ComponentResult = apply(plan, runner)
            results.append(result)
            self.component_finished.emit(component.name, result.ok)
            if not result.ok:
                break

        self.install_finished.emit(InstallResult(components=tuple(results)))
