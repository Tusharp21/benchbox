from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer.mariadb import (
    CONFIG_OVERRIDE_CONTENT,
    CONFIG_OVERRIDE_MARKER,
    MARIADB_PACKAGE,
    MariaDBComponent,
)


class FakeProbeRunner(CommandRunner):
    """Answers dpkg-query + systemctl probes from preset state."""

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
            return CommandResult(argv, 1, "", f"no packages found matching {package}", True)
        if argv[:2] == ("systemctl", "is-active"):
            service = argv[-1]
            rc = 0 if service in self._active else 3
            return CommandResult(argv, rc, "", "", True)
        raise AssertionError(f"unexpected probe command: {argv}")


@pytest.fixture
def missing_config_file(tmp_path: Path) -> Path:
    return tmp_path / "99-benchbox-frappe.cnf"


def _fresh_component(config_path: Path) -> MariaDBComponent:
    return MariaDBComponent(
        root_password="hunter2",
        probe_runner=FakeProbeRunner(),
        config_override_path=config_path,
    )


def test_plan_fresh_install_emits_full_sequence(missing_config_file: Path) -> None:
    component = _fresh_component(missing_config_file)
    plan = component.plan()
    descriptions = [s.description for s in plan.steps]

    # apt install, config write, enable, start (not restart — service not active), password set
    assert any("install mariadb-server" in d for d in descriptions)
    assert any("write Frappe charset override" in d for d in descriptions)
    assert "enable mariadb service on boot" in descriptions
    assert "start mariadb" in descriptions
    assert "set MariaDB root password" in descriptions


def test_plan_skips_install_when_package_present(missing_config_file: Path) -> None:
    component = MariaDBComponent(
        root_password="pw",
        probe_runner=FakeProbeRunner(installed_packages={MARIADB_PACKAGE}),
        config_override_path=missing_config_file,
    )
    plan = component.plan()
    install_step = plan.steps[0]
    assert install_step.skip_reason == "package present"
    # Password-set step is skipped entirely when already installed.
    assert not any("set MariaDB root password" in s.description for s in plan.steps)


def test_plan_skips_config_when_override_already_present(tmp_path: Path) -> None:
    existing = tmp_path / "99-benchbox-frappe.cnf"
    existing.write_text(f"{CONFIG_OVERRIDE_MARKER}\n[mysqld]\n", encoding="utf-8")
    component = MariaDBComponent(
        root_password="pw",
        probe_runner=FakeProbeRunner(installed_packages={MARIADB_PACKAGE}),
        config_override_path=existing,
    )
    plan = component.plan()
    config_steps = [s for s in plan.steps if "charset override" in s.description]
    assert len(config_steps) == 1
    assert config_steps[0].skip_reason == "config override present"


def test_plan_uses_restart_when_service_active(missing_config_file: Path) -> None:
    component = MariaDBComponent(
        root_password="pw",
        probe_runner=FakeProbeRunner(
            installed_packages={MARIADB_PACKAGE},
            active_services={"mariadb"},
        ),
        config_override_path=missing_config_file,
    )
    plan = component.plan()
    descriptions = [s.description for s in plan.steps]
    assert "restart mariadb to pick up config" in descriptions
    assert "start mariadb" not in descriptions


def test_config_write_step_pipes_content_via_stdin(missing_config_file: Path) -> None:
    component = _fresh_component(missing_config_file)
    plan = component.plan()

    config_step = next(s for s in plan.steps if "write Frappe charset override" in s.description)
    assert config_step.command == (
        "sudo",
        "tee",
        str(missing_config_file),
    )
    assert config_step.stdin == CONFIG_OVERRIDE_CONTENT
    assert "utf8mb4" in config_step.stdin


def test_password_step_pipes_sql_via_stdin_not_argv(missing_config_file: Path) -> None:
    component = MariaDBComponent(
        root_password="s3cr3t",
        probe_runner=FakeProbeRunner(),
        config_override_path=missing_config_file,
    )
    plan = component.plan()
    pw_step = next(s for s in plan.steps if s.description == "set MariaDB root password")

    # argv must not leak the password (it would show in ps aux)
    assert pw_step.command == ("sudo", "mysql", "-u", "root")
    assert "s3cr3t" not in " ".join(pw_step.command)
    assert pw_step.stdin is not None
    assert "ALTER USER 'root'@'localhost' IDENTIFIED BY 's3cr3t'" in pw_step.stdin
    assert "FLUSH PRIVILEGES" in pw_step.stdin


def test_password_step_escapes_embedded_single_quotes(missing_config_file: Path) -> None:
    component = MariaDBComponent(
        root_password="it's-fine",
        probe_runner=FakeProbeRunner(),
        config_override_path=missing_config_file,
    )
    plan = component.plan()
    pw_step = next(s for s in plan.steps if s.description == "set MariaDB root password")
    assert pw_step.stdin is not None
    assert "IDENTIFIED BY 'it''s-fine'" in pw_step.stdin


def test_use_sudo_false_drops_sudo(missing_config_file: Path) -> None:
    component = MariaDBComponent(
        root_password="pw",
        probe_runner=FakeProbeRunner(),
        config_override_path=missing_config_file,
        use_sudo=False,
    )
    plan = component.plan()
    for step in plan.steps:
        assert step.command[:1] != ("sudo",)


class ScriptedApplyRunner(CommandRunner):
    """Apply-side runner with pre-set exit codes; records stdin per call."""

    def __init__(self, returncodes: list[int]) -> None:
        super().__init__(dry_run=False)
        self._returncodes = list(returncodes)
        self._index = 0
        self.stdins: list[str | None] = []

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
        self.stdins.append(input)
        stderr = "boom" if rc != 0 else ""
        return CommandResult(tuple(command), rc, "", stderr, executed=True)


def test_apply_dry_run_marks_every_runnable_step(missing_config_file: Path) -> None:
    component = _fresh_component(missing_config_file)
    runner = CommandRunner(dry_run=True)

    plan = component.plan()
    result = component.apply(plan, runner)

    assert result.ok is True
    assert all(r.executed is False or r.skipped for r in result.results)
    # History must include every runnable step.
    assert len(runner.history) == len(plan.runnable_steps)


def test_apply_threads_stdin_to_runner(missing_config_file: Path) -> None:
    component = _fresh_component(missing_config_file)
    plan = component.plan()
    # Succeed on every step so we get the full stdin trace.
    runner = ScriptedApplyRunner(returncodes=[0] * len(plan.runnable_steps))

    component.apply(plan, runner)

    # The tee step and the mysql step must both have received stdin.
    non_empty_stdins = [s for s in runner.stdins if s]
    assert any("utf8mb4" in s for s in non_empty_stdins)
    assert any("ALTER USER" in s for s in non_empty_stdins)


def test_apply_short_circuits_on_first_failure(missing_config_file: Path) -> None:
    component = _fresh_component(missing_config_file)
    plan = component.plan()
    # Fail on step 1 (apt install)
    runner = ScriptedApplyRunner(returncodes=[1])

    result = component.apply(plan, runner)

    assert result.ok is False
    # One executed failure, no further steps (skipped steps at plan-start may
    # precede but fresh install has no skipped steps).
    executed = [r for r in result.results if r.executed]
    assert len(executed) == 1
    assert executed[0].error == "boom"
