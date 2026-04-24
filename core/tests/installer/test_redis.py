from __future__ import annotations

from collections.abc import Iterable

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer.redis import REDIS_PACKAGE, REDIS_SERVICE, RedisComponent


class FakeProbeRunner(CommandRunner):
    """Answer dpkg-query + systemctl probes from preset state."""

    def __init__(
        self,
        *,
        installed_packages: Iterable[str] = (),
        active_services: Iterable[str] = (),
    ) -> None:
        super().__init__(dry_run=False)
        self._installed = set(installed_packages)
        self._active = set(active_services)

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
        if argv[:2] == ("systemctl", "is-active"):
            service = argv[-1]
            rc = 0 if service in self._active else 3
            return CommandResult(argv, rc, "", "", True)
        raise AssertionError(f"unexpected probe command: {argv}")


def test_plan_fresh_emits_install_enable_start() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()
    descriptions = [s.description for s in plan.steps]

    assert any(f"install {REDIS_PACKAGE}" in d for d in descriptions)
    assert f"enable {REDIS_SERVICE} on boot" in descriptions
    assert f"start {REDIS_SERVICE}" in descriptions


def test_plan_skips_install_when_package_present() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner(installed_packages={REDIS_PACKAGE}))
    plan = component.plan()
    assert plan.steps[0].skip_reason == "package present"


def test_plan_skips_start_when_service_active() -> None:
    component = RedisComponent(
        probe_runner=FakeProbeRunner(
            installed_packages={REDIS_PACKAGE},
            active_services={REDIS_SERVICE},
        )
    )
    plan = component.plan()
    start_steps = [s for s in plan.steps if "running" in s.description or "start" in s.description]
    # Should contain the "already running" skip, not a runnable start step.
    assert any(s.skip_reason == "service active" for s in start_steps)
    assert not any(s.description == f"start {REDIS_SERVICE}" for s in start_steps)


def test_plan_uses_sudo_by_default() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()
    for step in plan.runnable_steps:
        assert step.command[:1] == ("sudo",), step.command


def test_plan_drops_sudo_when_disabled() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner(), use_sudo=False)
    plan = component.plan()
    for step in plan.runnable_steps:
        assert step.command[:1] != ("sudo",), step.command


def test_apply_dry_run_records_every_runnable_step() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner())
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


def test_apply_short_circuits_on_install_failure() -> None:
    component = RedisComponent(probe_runner=FakeProbeRunner())
    plan = component.plan()
    runner = ScriptedRunner(returncodes=[1])

    result = component.apply(plan, runner)

    assert result.ok is False
    executed = [r for r in result.results if r.executed]
    assert len(executed) == 1
    assert executed[0].error == "boom"
