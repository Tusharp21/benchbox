from __future__ import annotations

from dataclasses import dataclass, field

from benchbox_core.installer import (
    CommandRunner,
    ComponentPlan,
    ComponentResult,
    InstallResult,
    Step,
    StepResult,
)
from pytestqt.qtbot import QtBot

from benchbox_gui.workers import InstallWorker


@dataclass
class FakeComponent:
    """Minimal component for worker tests: succeeds or fails on demand."""

    name: str
    succeed: bool = True
    events: list[str] = field(default_factory=list)

    def plan(self) -> ComponentPlan:
        self.events.append("plan")
        return ComponentPlan(component=self.name, steps=(Step("run", ("true",)),))

    def apply(self, plan: ComponentPlan, runner: CommandRunner) -> ComponentResult:
        self.events.append("apply")
        step = plan.steps[0]
        rc = 0 if self.succeed else 1
        return ComponentResult(
            component=self.name,
            results=(
                StepResult(
                    step=step,
                    executed=True,
                    skipped=False,
                    returncode=rc,
                    error=None if self.succeed else "boom",
                ),
            ),
        )


def test_worker_emits_per_component_and_final_result(qtbot: QtBot) -> None:
    a = FakeComponent(name="a")
    b = FakeComponent(name="b")

    worker = InstallWorker([a, b])
    started: list[tuple[str, int, int]] = []
    finished: list[tuple[str, bool]] = []
    worker.component_started.connect(lambda n, i, t: started.append((n, i, t)))
    worker.component_finished.connect(lambda n, ok: finished.append((n, ok)))

    with qtbot.waitSignal(worker.install_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    assert [s[0] for s in started] == ["a", "b"]
    assert [f[0] for f in finished] == ["a", "b"]
    assert all(f[1] for f in finished)
    result = blocker.args[0]
    assert isinstance(result, InstallResult)
    assert result.ok is True


def test_worker_short_circuits_on_failure(qtbot: QtBot) -> None:
    a = FakeComponent(name="a", succeed=False)
    b = FakeComponent(name="b")

    worker = InstallWorker([a, b])
    with qtbot.waitSignal(worker.install_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    result = blocker.args[0]
    assert result.ok is False
    # Only 'a' ran — 'b' should never have been asked to plan/apply.
    assert b.events == []
