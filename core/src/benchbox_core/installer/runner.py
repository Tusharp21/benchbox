"""Sequence components through plan -> apply, stop on first failure."""

from __future__ import annotations

from collections.abc import Sequence

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    Component,
    ComponentResult,
    InstallResult,
)
from benchbox_core.logs import get_logger

_log = get_logger(__name__)


def install(
    components: Sequence[Component],
    *,
    runner: CommandRunner | None = None,
    dry_run: bool = False,
) -> InstallResult:
    active_runner = runner if runner is not None else CommandRunner(dry_run=dry_run)

    results: list[ComponentResult] = []
    for component in components:
        _log.debug("[%s] planning", component.name)
        plan = component.plan()
        runnable = len(plan.runnable_steps)
        _log.debug("[%s] %d step(s) to run", component.name, runnable)

        apply = getattr(component, "apply", None)
        if apply is None:
            raise TypeError(f"component {component.name!r} does not implement apply(plan, runner)")

        result: ComponentResult = apply(plan, active_runner)
        results.append(result)
        if not result.ok:
            _log.error("[%s] failed; aborting remaining components", component.name)
            break
        _log.debug("[%s] done", component.name)

    return InstallResult(components=tuple(results))
