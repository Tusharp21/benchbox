"""Shared dataclasses and the ``Component`` protocol for the installer.

Kept deliberately small: every component speaks the same ``plan()`` /
``apply()`` shape so the runner, the CLI, and eventually the Tauri GUI can
all consume progress without knowing which component produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Step:
    """A single unit of work inside a component.

    ``command`` is the argv to execute. If ``skip_reason`` is set, the step is
    already satisfied (e.g. package already installed) and ``apply()`` will
    record it as skipped instead of running the command.
    """

    description: str
    command: tuple[str, ...]
    skip_reason: str | None = None


@dataclass(frozen=True)
class ComponentPlan:
    """What a component *would* do. Pure, no side effects."""

    component: str
    steps: tuple[Step, ...]

    @property
    def runnable_steps(self) -> tuple[Step, ...]:
        return tuple(s for s in self.steps if s.skip_reason is None)


@dataclass(frozen=True)
class StepResult:
    step: Step
    executed: bool
    skipped: bool
    returncode: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        if self.skipped:
            return True
        if self.error is not None:
            return False
        return self.returncode == 0


@dataclass(frozen=True)
class ComponentResult:
    component: str
    results: tuple[StepResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failed(self) -> tuple[StepResult, ...]:
        return tuple(r for r in self.results if not r.ok)


@dataclass(frozen=True)
class InstallResult:
    components: tuple[ComponentResult, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.components)

    @property
    def failed_component(self) -> ComponentResult | None:
        return next((c for c in self.components if not c.ok), None)


@runtime_checkable
class Component(Protocol):
    """Everything the runner needs from a component.

    ``name`` is a stable short identifier (``"apt"``, ``"mariadb"``). ``plan``
    is expected to be cheap and side-effect-free — the CLI will call it to
    show a dry-run preview.
    """

    name: str

    def plan(self) -> ComponentPlan: ...
