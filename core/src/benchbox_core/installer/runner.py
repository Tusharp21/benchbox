"""Orchestrator: sequences components through plan → apply.

Short-circuits on the first component that fails — the caller decides how to
present the failure (CLI prints a diagnostic + log path, GUI surfaces it on
the failing component's card).
"""

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
    """Run each component's plan → apply in order; stop at first failure.

    Components are expected to implement ``apply(plan, runner)`` in addition
    to the ``Component`` protocol's ``plan()``. We use a structural cast here
    rather than widening the protocol because ``apply`` signatures will grow
    extra kwargs per component (e.g. MariaDB root password) that the runner
    shouldn't know about.
    """
    active_runner = runner if runner is not None else CommandRunner(dry_run=dry_run)

    results: list[ComponentResult] = []
    for component in components:
        _log.info("[%s] planning", component.name)
        plan = component.plan()
        runnable = len(plan.runnable_steps)
        _log.info("[%s] %d step(s) to run", component.name, runnable)

        apply = getattr(component, "apply", None)
        if apply is None:
            raise TypeError(f"component {component.name!r} does not implement apply(plan, runner)")

        result: ComponentResult = apply(plan, active_runner)
        results.append(result)
        if not result.ok:
            _log.error("[%s] failed; aborting remaining components", component.name)
            break
        _log.info("[%s] done", component.name)

    return InstallResult(components=tuple(results))
