from __future__ import annotations

import json
from collections.abc import Iterable

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer.bench_cli import (
    FRAPPE_BENCH_PIPX_NAME,
    PIPX_PACKAGE,
    BenchCliComponent,
)


class FakeProbeRunner(CommandRunner):
    """Answers dpkg-query + pipx list probes from preset state."""

    def __init__(
        self,
        *,
        installed_packages: Iterable[str] = (),
        pipx_venvs: Iterable[str] = (),
        pipx_list_exit: int = 0,
    ) -> None:
        super().__init__(dry_run=False)
        self._installed = set(installed_packages)
        self._venvs = set(pipx_venvs)
        self._pipx_list_exit = pipx_list_exit

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        if argv[:1] == ("dpkg-query",):
            package = argv[-1]
            if package in self._installed:
                return CommandResult(argv, 0, "install ok installed", "", True)
            return CommandResult(argv, 1, "", "not found", True)
        if argv[:2] == ("pipx", "list"):
            if self._pipx_list_exit != 0:
                return CommandResult(argv, self._pipx_list_exit, "", "pipx not found", True)
            payload: dict[str, dict[str, dict[str, object]]] = {
                "venvs": {name: {} for name in self._venvs}
            }
            return CommandResult(argv, 0, json.dumps(payload), "", True)
        raise AssertionError(f"unexpected probe command: {argv}")


def test_plan_fresh_emits_full_sequence() -> None:
    component = BenchCliComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()

    descriptions = [s.description for s in plan.steps]
    assert any(f"install {PIPX_PACKAGE}" in d for d in descriptions)
    assert any("ensure ~/.local/bin is on PATH" in d for d in descriptions)
    assert any(f"install {FRAPPE_BENCH_PIPX_NAME} via pipx" in d for d in descriptions)


def test_plan_skips_pipx_when_present() -> None:
    component = BenchCliComponent(probe_runner=FakeProbeRunner(installed_packages={PIPX_PACKAGE}))
    plan = component.plan()

    assert plan.steps[0].skip_reason == "pipx present"


def test_plan_skips_bench_when_already_in_pipx() -> None:
    component = BenchCliComponent(
        probe_runner=FakeProbeRunner(
            installed_packages={PIPX_PACKAGE},
            pipx_venvs={FRAPPE_BENCH_PIPX_NAME},
        )
    )
    plan = component.plan()

    bench_steps = [s for s in plan.steps if FRAPPE_BENCH_PIPX_NAME in s.description]
    assert len(bench_steps) == 1
    assert bench_steps[0].skip_reason == "frappe-bench present"


def test_plan_still_installs_bench_when_pipx_list_fails() -> None:
    # If pipx itself errors out, we can't tell whether bench is present;
    # fall through to the install step rather than silently skip.
    component = BenchCliComponent(
        probe_runner=FakeProbeRunner(
            installed_packages={PIPX_PACKAGE},
            pipx_list_exit=1,
        )
    )
    plan = component.plan()

    bench_install_step = next(
        s for s in plan.steps if f"install {FRAPPE_BENCH_PIPX_NAME} via pipx" in s.description
    )
    assert bench_install_step.skip_reason is None


def test_plan_ensurepath_runs_unconditionally() -> None:
    # pipx already there, bench already there — ensurepath should still show
    # up because it's cheap and idempotent.
    component = BenchCliComponent(
        probe_runner=FakeProbeRunner(
            installed_packages={PIPX_PACKAGE},
            pipx_venvs={FRAPPE_BENCH_PIPX_NAME},
        )
    )
    plan = component.plan()

    ensurepath_step = next(s for s in plan.steps if "ensure ~/.local/bin" in s.description)
    assert ensurepath_step.skip_reason is None
    assert ensurepath_step.command == ("pipx", "ensurepath")


def test_plan_pipx_commands_never_use_sudo() -> None:
    component = BenchCliComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()

    pipx_steps = [s for s in plan.runnable_steps if s.command and s.command[0] == "pipx"]
    assert pipx_steps, "expected at least one pipx step"
    for step in pipx_steps:
        # pipx is per-user; sudo-installing it would put bench in /root.
        assert "sudo" not in step.command


def test_apply_dry_run_records_runnable_steps() -> None:
    component = BenchCliComponent(probe_runner=FakeProbeRunner())
    runner = CommandRunner(dry_run=True)

    plan = component.plan()
    result = component.apply(plan, runner)

    assert result.ok is True
    assert len(runner.history) == len(plan.runnable_steps)


class ScriptedRunner(CommandRunner):
    def __init__(self, returncodes: list[int]) -> None:
        super().__init__(dry_run=False)
        self._returncodes = list(returncodes)
        self._index = 0

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        rc = self._returncodes[self._index]
        self._index += 1
        return CommandResult(tuple(command), rc, "", "boom" if rc else "", True)


def test_apply_short_circuits_on_failure() -> None:
    component = BenchCliComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()
    runner = ScriptedRunner(returncodes=[1])

    result = component.apply(plan, runner)

    assert result.ok is False
    executed = [r for r in result.results if r.executed]
    assert len(executed) == 1
    assert executed[0].error == "boom"
