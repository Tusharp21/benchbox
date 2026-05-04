"""Component protocol + result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Step:
    description: str
    command: tuple[str, ...]
    stdin: str | None = None
    skip_reason: str | None = None


@dataclass(frozen=True)
class ComponentPlan:
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
    name: str

    def plan(self) -> ComponentPlan: ...
