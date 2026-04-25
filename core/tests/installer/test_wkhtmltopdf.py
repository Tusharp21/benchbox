from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from benchbox_core.installer._run import CommandResult, CommandRunner

if TYPE_CHECKING:
    from pathlib import Path
from benchbox_core.installer.wkhtmltopdf import (
    UBUNTU_PACKAGE,
    WKHTMLTOPDF_VERSION,
    UnsupportedWkhtmltopdfPlatform,
    WkhtmltopdfComponent,
    deb_filename,
    deb_url,
    probe_wkhtmltopdf,
)

# --- URL / filename matrix ----------------------------------------


def test_deb_filename_jammy_amd64() -> None:
    assert deb_filename("22.04", "x86_64") == f"wkhtmltox_{WKHTMLTOPDF_VERSION}.jammy_amd64.deb"


def test_deb_filename_noble_falls_back_to_jammy() -> None:
    # Upstream packaging doesn't ship a noble build; we reuse jammy's.
    assert "jammy" in deb_filename("24.04", "x86_64")


def test_deb_filename_arm64_mapping() -> None:
    assert deb_filename("22.04", "aarch64").endswith("_arm64.deb")


def test_deb_url_points_to_upstream_release() -> None:
    url = deb_url("22.04", "x86_64")
    assert url.startswith("https://github.com/wkhtmltopdf/packaging/releases/download/")
    assert WKHTMLTOPDF_VERSION in url
    assert url.endswith(".deb")


def test_unsupported_ubuntu_version_raises() -> None:
    with pytest.raises(UnsupportedWkhtmltopdfPlatform):
        deb_filename("20.04", "x86_64")


def test_unsupported_arch_raises() -> None:
    with pytest.raises(UnsupportedWkhtmltopdfPlatform):
        deb_filename("22.04", "riscv64")


# --- probe --------------------------------------------------------


class FixedRunner(CommandRunner):
    """Always returns a preset CommandResult for the first run() call."""

    def __init__(self, result: CommandResult) -> None:
        super().__init__(dry_run=False)
        self._result = result

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        return CommandResult(
            command=tuple(command),
            returncode=self._result.returncode,
            stdout=self._result.stdout,
            stderr=self._result.stderr,
            executed=self._result.executed,
        )


def _runner_with_version(line: str) -> CommandRunner:
    return FixedRunner(CommandResult(("wkhtmltopdf", "--version"), 0, line, "", True))


def _missing_runner() -> CommandRunner:
    return FixedRunner(CommandResult(("wkhtmltopdf", "--version"), 127, "", "not found", True))


def test_probe_missing_when_binary_absent() -> None:
    result = probe_wkhtmltopdf(_missing_runner())
    assert result.installed is False
    assert result.patched is False


def test_probe_unpatched() -> None:
    result = probe_wkhtmltopdf(_runner_with_version("wkhtmltopdf 0.12.6"))
    assert result.installed is True
    assert result.patched is False
    assert result.raw_version is not None


def test_probe_patched() -> None:
    result = probe_wkhtmltopdf(_runner_with_version("wkhtmltopdf 0.12.6.1 (with patched qt)"))
    assert result.installed is True
    assert result.patched is True


# --- plan ---------------------------------------------------------


def _component_with_probe(probe: CommandRunner) -> WkhtmltopdfComponent:
    return WkhtmltopdfComponent(
        ubuntu_version="22.04",
        machine_arch="x86_64",
        probe_runner=probe,
    )


def test_plan_missing_binary_emits_download_and_install() -> None:
    component = _component_with_probe(_missing_runner())
    plan = component.plan()

    descriptions = [s.description for s in plan.steps]
    assert any("download patched-qt wkhtmltopdf" in d for d in descriptions)
    assert any(d.startswith("install wkhtmltox_") for d in descriptions)
    # No purge step when there's nothing to purge.
    assert not any("purge" in d for d in descriptions)


def test_plan_patched_build_is_full_skip() -> None:
    component = _component_with_probe(
        _runner_with_version("wkhtmltopdf 0.12.6.1 (with patched qt)")
    )
    plan = component.plan()

    assert len(plan.steps) == 1
    assert plan.steps[0].skip_reason == "patched build present"
    assert plan.runnable_steps == ()


def test_plan_unpatched_inserts_purge_before_install() -> None:
    component = _component_with_probe(_runner_with_version("wkhtmltopdf 0.12.6"))
    plan = component.plan()

    descriptions = [s.description for s in plan.steps]
    assert any("purge unpatched wkhtmltopdf" in d for d in descriptions)

    # Purge must come before download, download before install.
    purge_idx = next(i for i, d in enumerate(descriptions) if "purge" in d)
    download_idx = next(i for i, d in enumerate(descriptions) if "download" in d)
    install_idx = next(i for i, d in enumerate(descriptions) if d.startswith("install "))
    assert purge_idx < download_idx < install_idx


def test_plan_purge_targets_ubuntu_package_not_upstream() -> None:
    component = _component_with_probe(_runner_with_version("wkhtmltopdf 0.12.6"))
    plan = component.plan()
    purge_step = next(s for s in plan.steps if "purge" in s.description)
    assert UBUNTU_PACKAGE in purge_step.command


def test_plan_download_command_has_fail_flags() -> None:
    component = _component_with_probe(_missing_runner())
    plan = component.plan()
    download_step = next(s for s in plan.steps if "download" in s.description)
    # curl must fail hard on HTTP errors so a 404 doesn't silently succeed.
    assert download_step.command[0] == "curl"
    assert "-fsSL" in download_step.command


def test_plan_install_command_references_downloaded_file() -> None:
    component = _component_with_probe(_missing_runner())
    plan = component.plan()
    install_step = next(s for s in plan.steps if s.description.startswith("install wkhtmltox_"))
    # Install path should be the /tmp deb (apt install ./path.deb pattern).
    assert any(part.endswith(".deb") and part.startswith("/") for part in install_step.command)


def test_plan_raises_when_ubuntu_version_missing() -> None:
    component = WkhtmltopdfComponent(
        ubuntu_version="", machine_arch="x86_64", probe_runner=_missing_runner()
    )
    with pytest.raises(UnsupportedWkhtmltopdfPlatform):
        component.plan()


def test_plan_respects_use_sudo_false() -> None:
    component = WkhtmltopdfComponent(
        ubuntu_version="22.04",
        machine_arch="x86_64",
        probe_runner=_runner_with_version("wkhtmltopdf 0.12.6"),
        use_sudo=False,
    )
    plan = component.plan()
    for step in plan.runnable_steps:
        assert step.command[:1] != ("sudo",), step.command


# --- apply --------------------------------------------------------


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
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        rc = self._returncodes[self._index]
        self._index += 1
        return CommandResult(tuple(command), rc, "", "boom" if rc else "", True)


def test_apply_dry_run_records_all_runnable_steps() -> None:
    component = _component_with_probe(_missing_runner())
    runner = CommandRunner(dry_run=True)

    plan = component.plan()
    result = component.apply(plan, runner)

    assert result.ok is True
    assert len(runner.history) == len(plan.runnable_steps)


def test_apply_short_circuits_on_download_failure() -> None:
    component = _component_with_probe(_missing_runner())
    plan = component.plan()
    # mkdir cache succeeds (rc=0), then curl download fails (rc=1).
    runner = ScriptedRunner(returncodes=[0, 1])

    result = component.apply(plan, runner)

    assert result.ok is False
    executed = [r for r in result.results if r.executed]
    assert len(executed) == 2
    assert executed[-1].error == "boom"
