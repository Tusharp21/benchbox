"""QThread workers that keep long-running core calls off the UI thread.

The installer sequence takes minutes and writes to apt; the UI must stay
responsive while it runs. Each worker here wraps a single core operation
and surfaces progress via Qt signals.
"""

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
    """Run a no-arg callable off the UI thread; emit result or exception.

    Used for the handful of single-shot core calls the GUI needs to spawn
    without blocking the event loop: ``create_bench``, ``create_site``,
    ``drop_site``, ``get_app``, ``install_app``, ``uninstall_app``.

    Callers build a lambda that closes over the real args and then hook
    into ``succeeded(object)`` (the return value) or ``failed(object)``
    (the exception). Both signals fire on the UI thread.
    """

    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as exc:  # noqa: BLE001 — surface anything the op raises
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


class StreamingOpWorker(QThread):
    """Run a streaming core operation off the UI thread.

    The operation is a callable that accepts a single ``line_callback``
    argument and returns a result. Inside the worker we run the callable
    with ``self.line_received.emit`` as that callback, so the operation's
    underlying ``CommandRunner`` pipes stdout lines back to the UI thread
    via Qt's queued-connection signal delivery.

    Used for the get-app / new-app dialogs where the user wants to watch
    git-clone + pip-install output stream live.
    """

    line_received = Signal(str)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, operation: Callable[[Callable[[str], None]], Any]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation(self.line_received.emit)
        except Exception as exc:  # noqa: BLE001 — surface anything the op raises
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


class InstallWorker(QThread):
    """Run :func:`benchbox_core.installer.install` off the UI thread.

    Signals:
    - ``component_started(str, int, int)`` — component name, index, total
    - ``component_finished(str, bool)`` — component name, ok flag
    - ``install_finished(object)`` — the full ``InstallResult``

    The worker calls each component's ``plan()`` + ``apply()`` directly
    instead of going through ``install()`` so we can emit per-component
    events as they happen, not just at the end.
    """

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

    def run(self) -> None:  # noqa: D401 — QThread override name
        results: list[ComponentResult] = []
        runner = CommandRunner(dry_run=self._dry_run)
        total = len(self._components)

        for idx, component in enumerate(self._components):
            self.component_started.emit(component.name, idx, total)
            plan: ComponentPlan = component.plan()
            apply = getattr(component, "apply", None)
            if apply is None:
                # Shouldn't happen for our components; fail safely.
                results.append(ComponentResult(component=component.name, results=()))
                self.component_finished.emit(component.name, False)
                break
            result: ComponentResult = apply(plan, runner)
            results.append(result)
            self.component_finished.emit(component.name, result.ok)
            if not result.ok:
                break

        self.install_finished.emit(InstallResult(components=tuple(results)))
