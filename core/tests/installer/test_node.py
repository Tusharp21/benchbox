from __future__ import annotations

from pathlib import Path

import pytest

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.installer.node import NVM_VERSION, NodeComponent


@pytest.fixture
def empty_nvm(tmp_path: Path) -> Path:
    """A directory that will serve as nvm_dir but has no nvm files in it."""
    return tmp_path / "nvm"


def _install_nvm_marker(nvm_dir: Path) -> None:
    nvm_dir.mkdir(parents=True, exist_ok=True)
    (nvm_dir / "nvm.sh").write_text("# fake nvm\n", encoding="utf-8")


def _install_node_version(nvm_dir: Path, version: str) -> Path:
    node_dir = nvm_dir / "versions" / "node" / version
    (node_dir / "bin").mkdir(parents=True, exist_ok=True)
    (node_dir / "bin" / "node").write_text("#!/bin/sh\n", encoding="utf-8")
    return node_dir


def _install_yarn(nvm_dir: Path, node_dir: Path) -> None:
    del nvm_dir  # unused, kept for symmetry
    (node_dir / "bin" / "yarn").write_text("#!/bin/sh\n", encoding="utf-8")


# --- plan ----------------------------------------------------------


def test_plan_fresh_emits_all_three_steps(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm)
    plan = component.plan()

    descriptions = [s.description for s in plan.steps]
    assert any(f"install nvm {NVM_VERSION}" in d for d in descriptions)
    assert any("install Node 18 via nvm" in d for d in descriptions)
    assert any("install yarn globally via npm" in d for d in descriptions)


def test_plan_skips_nvm_when_present(empty_nvm: Path) -> None:
    _install_nvm_marker(empty_nvm)
    component = NodeComponent(nvm_dir=empty_nvm)
    plan = component.plan()

    first = plan.steps[0]
    assert first.skip_reason == "nvm present"


def test_plan_skips_node_when_matching_major_present(empty_nvm: Path) -> None:
    _install_nvm_marker(empty_nvm)
    _install_node_version(empty_nvm, "v18.20.0")
    component = NodeComponent(nvm_dir=empty_nvm, install_yarn=False)
    plan = component.plan()

    node_steps = [s for s in plan.steps if "Node 18" in s.description]
    assert len(node_steps) == 1
    assert node_steps[0].skip_reason is not None


def test_plan_does_not_skip_node_when_major_mismatches(empty_nvm: Path) -> None:
    _install_nvm_marker(empty_nvm)
    _install_node_version(empty_nvm, "v16.20.0")  # wrong major
    component = NodeComponent(nvm_dir=empty_nvm, node_major="18", install_yarn=False)
    plan = component.plan()

    node_steps = [s for s in plan.steps if "Node 18" in s.description]
    assert len(node_steps) == 1
    assert node_steps[0].skip_reason is None


def test_plan_skips_yarn_when_binary_present(empty_nvm: Path) -> None:
    _install_nvm_marker(empty_nvm)
    node_dir = _install_node_version(empty_nvm, "v18.20.0")
    _install_yarn(empty_nvm, node_dir)
    component = NodeComponent(nvm_dir=empty_nvm)
    plan = component.plan()

    yarn_step = next(s for s in plan.steps if s.description.startswith("yarn already"))
    assert yarn_step.skip_reason == "yarn present"


def test_plan_omits_yarn_when_disabled(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm, install_yarn=False)
    plan = component.plan()

    # None of the step descriptions should mention yarn. We can't substring-
    # match because tmp_path may contain the test name.
    assert not any(
        s.description.startswith("yarn") or "install yarn" in s.description for s in plan.steps
    )


def test_plan_honours_custom_node_major(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm, node_major="20", install_yarn=False)
    plan = component.plan()

    assert any("install Node 20" in s.description for s in plan.steps)


def test_plan_never_uses_sudo(empty_nvm: Path) -> None:
    # Node/nvm is per-user — none of the argv should start with sudo.
    component = NodeComponent(nvm_dir=empty_nvm)
    plan = component.plan()

    for step in plan.runnable_steps:
        assert step.command[:1] != ("sudo",), step.command


def test_plan_nvm_install_uses_login_bash_and_pinned_url(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm)
    plan = component.plan()

    nvm_step = plan.steps[0]
    assert nvm_step.command[:2] == ("bash", "-lc")
    # Exact URL must be present (not built at call time); curl flags are safe.
    script = nvm_step.command[2]
    assert NVM_VERSION in script
    assert "curl -fsSL" in script
    assert "| bash" in script


def test_plan_node_install_sources_nvm_from_given_dir(empty_nvm: Path) -> None:
    _install_nvm_marker(empty_nvm)
    component = NodeComponent(nvm_dir=empty_nvm, install_yarn=False)
    plan = component.plan()

    node_step = next(s for s in plan.steps if "install Node" in s.description)
    script = node_step.command[2]
    assert str(empty_nvm) in script
    assert "nvm.sh" in script
    assert "nvm install 18" in script


# --- apply ---------------------------------------------------------


def test_apply_dry_run_records_all_runnable_steps(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm)
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
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        rc = self._returncodes[self._index]
        self._index += 1
        return CommandResult(tuple(command), rc, "", "boom" if rc else "", True)


def test_apply_short_circuits_on_failure(empty_nvm: Path) -> None:
    component = NodeComponent(nvm_dir=empty_nvm, install_yarn=True)
    plan = component.plan()
    # Fail on the first real command (nvm install).
    runner = ScriptedRunner(returncodes=[1])

    result = component.apply(plan, runner)

    assert result.ok is False
    executed = [r for r in result.results if r.executed]
    assert len(executed) == 1
    assert executed[0].error == "boom"
