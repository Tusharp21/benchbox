from __future__ import annotations

from collections.abc import Iterable

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer.apt import BASE_PACKAGES, AptComponent


class FakeProbeRunner(CommandRunner):
    """Probe runner that answers dpkg-query from a preset set."""

    def __init__(self, installed: Iterable[str]) -> None:
        super().__init__(dry_run=False)
        self._installed = set(installed)

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        if len(argv) >= 4 and argv[0] == "dpkg-query":
            package = argv[-1]
            if package in self._installed:
                return CommandResult(argv, 0, "install ok installed", "", executed=True)
            return CommandResult(argv, 1, "", f"no packages found matching {package}", True)
        raise AssertionError(f"unexpected probe command: {argv}")


def test_plan_is_noop_when_all_packages_installed() -> None:
    probe = FakeProbeRunner(installed=BASE_PACKAGES)
    component = AptComponent(probe_runner=probe)

    plan = component.plan()

    assert plan.component == "apt"
    assert len(plan.steps) == 1
    assert plan.steps[0].skip_reason == "nothing to install"
    assert plan.runnable_steps == ()


def test_plan_emits_update_plus_install_for_missing() -> None:
    probe = FakeProbeRunner(installed=set(BASE_PACKAGES) - {"git", "curl"})
    component = AptComponent(probe_runner=probe)

    plan = component.plan()

    assert len(plan.steps) == 2
    update, install = plan.steps
    assert update.command == ("sudo", "apt-get", "update")
    assert install.command[:5] == ("sudo", "apt-get", "install", "-y", "--no-install-recommends")
    # Order must match iteration order of BASE_PACKAGES.
    assert install.command[5:] == ("git", "curl")


def test_plan_respects_use_sudo_false() -> None:
    probe = FakeProbeRunner(installed=set(BASE_PACKAGES) - {"git"})
    component = AptComponent(probe_runner=probe, use_sudo=False)

    plan = component.plan()

    assert plan.steps[0].command == ("apt-get", "update")
    assert plan.steps[1].command[0] == "apt-get"


def test_plan_honours_custom_package_set() -> None:
    probe = FakeProbeRunner(installed=())
    component = AptComponent(probe_runner=probe, packages=("htop", "jq"))

    plan = component.plan()

    assert plan.steps[1].command[-2:] == ("htop", "jq")


def test_apply_executes_every_runnable_step_in_dry_run() -> None:
    probe = FakeProbeRunner(installed=set(BASE_PACKAGES) - {"git"})
    component = AptComponent(probe_runner=probe)
    runner = CommandRunner(dry_run=True)

    plan = component.plan()
    result = component.apply(plan, runner)

    assert result.component == "apt"
    assert len(result.results) == 2
    assert all(r.executed is False for r in result.results)  # dry-run
    assert result.ok is True
    assert [tuple(c.command) for c in runner.history] == [tuple(s.command) for s in plan.steps]


def test_apply_marks_skip_step_as_skipped() -> None:
    probe = FakeProbeRunner(installed=BASE_PACKAGES)
    component = AptComponent(probe_runner=probe)
    runner = CommandRunner(dry_run=True)

    plan = component.plan()
    result = component.apply(plan, runner)

    assert len(result.results) == 1
    only = result.results[0]
    assert only.skipped is True
    assert only.executed is False
    assert runner.history == ()  # nothing dispatched


class ScriptedApplyRunner(CommandRunner):
    """Apply-side runner that returns pre-set exit codes per command index."""

    def __init__(self, returncodes: list[int]) -> None:
        super().__init__(dry_run=False)
        self._returncodes = list(returncodes)
        self._index = 0

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        rc = self._returncodes[self._index]
        self._index += 1
        stderr = "boom" if rc != 0 else ""
        return CommandResult(tuple(command), rc, "", stderr, executed=True)


def test_apply_short_circuits_on_failure() -> None:
    probe = FakeProbeRunner(installed=set(BASE_PACKAGES) - {"git"})
    component = AptComponent(probe_runner=probe)
    # apt-get update fails -> install should not run
    runner = ScriptedApplyRunner(returncodes=[1])

    plan = component.plan()
    result = component.apply(plan, runner)

    assert result.ok is False
    assert len(result.results) == 1  # install step skipped
    failed = result.results[0]
    assert failed.returncode == 1
    assert failed.error == "boom"
