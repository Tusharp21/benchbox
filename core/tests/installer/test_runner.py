from __future__ import annotations

from dataclasses import dataclass, field

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)
from benchbox_core.installer.runner import install


@dataclass
class FakeComponent:
    """Minimal Component used to exercise the orchestrator."""

    name: str
    plan_steps: tuple[Step, ...] = ()
    should_succeed: bool = True
    calls: list[str] = field(default_factory=list)

    def plan(self) -> ComponentPlan:
        self.calls.append("plan")
        return ComponentPlan(component=self.name, steps=self.plan_steps)

    def apply(self, plan: ComponentPlan, runner: CommandRunner) -> ComponentResult:
        self.calls.append("apply")
        step = plan.steps[0] if plan.steps else Step("noop", ())
        rc = 0 if self.should_succeed else 1
        return ComponentResult(
            component=self.name,
            results=(
                StepResult(
                    step=step,
                    executed=True,
                    skipped=False,
                    returncode=rc,
                    error=None if self.should_succeed else "boom",
                ),
            ),
        )


def _step() -> Step:
    return Step("run", ("true",))


def test_install_runs_all_components_in_order() -> None:
    a = FakeComponent(name="a", plan_steps=(_step(),))
    b = FakeComponent(name="b", plan_steps=(_step(),))

    result = install([a, b])

    assert result.ok is True
    assert [c.component for c in result.components] == ["a", "b"]
    assert a.calls == ["plan", "apply"]
    assert b.calls == ["plan", "apply"]


def test_install_short_circuits_on_failure() -> None:
    a = FakeComponent(name="a", plan_steps=(_step(),), should_succeed=False)
    b = FakeComponent(name="b", plan_steps=(_step(),))

    result = install([a, b])

    assert result.ok is False
    assert [c.component for c in result.components] == ["a"]
    assert result.failed_component is not None
    assert result.failed_component.component == "a"
    assert b.calls == []  # never reached


def test_install_uses_provided_runner() -> None:
    a = FakeComponent(name="a", plan_steps=(_step(),))
    custom = CommandRunner(dry_run=True)

    result = install([a], runner=custom)

    assert result.ok is True
    # Runner was threaded through; FakeComponent.apply doesn't call it, but the
    # installer must have accepted a provided runner without raising.


def test_install_dry_run_flag_creates_dry_runner() -> None:
    received: list[CommandRunner] = []

    @dataclass
    class SpyComponent:
        name: str = "spy"

        def plan(self) -> ComponentPlan:
            return ComponentPlan(component=self.name, steps=(_step(),))

        def apply(self, plan: ComponentPlan, runner: CommandRunner) -> ComponentResult:
            received.append(runner)
            return ComponentResult(
                component=self.name,
                results=(
                    StepResult(
                        step=plan.steps[0],
                        executed=False,
                        skipped=False,
                        returncode=0,
                        error=None,
                    ),
                ),
            )

    install([SpyComponent()], dry_run=True)

    assert len(received) == 1
    assert received[0].dry_run is True


def test_install_empty_component_list_is_ok() -> None:
    result = install([])
    assert result.ok is True
    assert result.components == ()
