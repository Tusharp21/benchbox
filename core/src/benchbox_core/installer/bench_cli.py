"""bench CLI installer — provision the ``frappe-bench`` Python package via pipx.

``frappe-bench`` is the tool that runs ``bench init``, ``bench new-site``,
and every per-bench operation. We install it through pipx so that:
- it gets its own isolated venv (avoids Ubuntu 22.04+ PEP 668 friction)
- the ``bench`` binary lands on the user's PATH automatically
- upgrades stay independent of the system Python

Steps are emitted only if their state has drifted, matching the idempotent
plan/apply contract every other installer component follows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)

PIPX_PACKAGE: str = "pipx"
FRAPPE_BENCH_PIPX_NAME: str = "frappe-bench"


def _dpkg_installed(runner: CommandRunner, package: str) -> bool:
    result = runner.run(["dpkg-query", "-W", "-f=${Status}", package], check=False)
    if not result.executed or result.returncode != 0:
        return False
    return result.stdout.strip() == "install ok installed"


def _pipx_has_bench(runner: CommandRunner) -> bool:
    """Return True iff ``pipx list --json`` reports frappe-bench as installed."""
    result = runner.run(["pipx", "list", "--json"], check=False)
    if not result.executed or result.returncode != 0:
        return False
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    venvs = parsed.get("venvs") if isinstance(parsed, dict) else None
    if not isinstance(venvs, dict):
        return False
    return FRAPPE_BENCH_PIPX_NAME in venvs


@dataclass
class BenchCliComponent:
    """Install pipx (if missing) and then ``frappe-bench`` through it."""

    name: str = field(default="bench-cli", init=False)
    probe_runner: CommandRunner = field(default_factory=lambda: CommandRunner(quiet=True))
    use_sudo: bool = True

    def _sudo(self, argv: list[str]) -> tuple[str, ...]:
        return tuple(["sudo", *argv]) if self.use_sudo else tuple(argv)

    def plan(self) -> ComponentPlan:
        steps: list[Step] = []

        pipx_installed = _dpkg_installed(self.probe_runner, PIPX_PACKAGE)
        if pipx_installed:
            steps.append(
                Step(
                    description="pipx already installed",
                    command=(),
                    skip_reason="pipx present",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"install {PIPX_PACKAGE}",
                    command=self._sudo(
                        [
                            "apt-get",
                            "install",
                            "-y",
                            "--no-install-recommends",
                            PIPX_PACKAGE,
                        ]
                    ),
                )
            )

        # ``pipx ensurepath`` is idempotent by design and cheap, so we run it
        # unconditionally. It's the only way to be sure the user's shell will
        # pick up ~/.local/bin on their next login.
        steps.append(
            Step(
                description="ensure ~/.local/bin is on PATH for future shells",
                command=("pipx", "ensurepath"),
            )
        )

        if pipx_installed and _pipx_has_bench(self.probe_runner):
            steps.append(
                Step(
                    description=f"{FRAPPE_BENCH_PIPX_NAME} already installed via pipx",
                    command=(),
                    skip_reason="frappe-bench present",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"install {FRAPPE_BENCH_PIPX_NAME} via pipx",
                    command=("pipx", "install", FRAPPE_BENCH_PIPX_NAME),
                )
            )

        return ComponentPlan(component=self.name, steps=tuple(steps))

    def apply(self, plan: ComponentPlan, runner: CommandRunner) -> ComponentResult:
        results: list[StepResult] = []
        for step in plan.steps:
            if step.skip_reason is not None:
                results.append(
                    StepResult(
                        step=step,
                        executed=False,
                        skipped=True,
                        returncode=None,
                        error=None,
                    )
                )
                continue

            cmd_result = runner.run(list(step.command), input=step.stdin)
            error: str | None = None
            if cmd_result.executed and cmd_result.returncode != 0:
                error = cmd_result.stderr.strip() or None

            results.append(
                StepResult(
                    step=step,
                    executed=cmd_result.executed,
                    skipped=False,
                    returncode=cmd_result.returncode,
                    error=error,
                )
            )
            if cmd_result.executed and cmd_result.returncode != 0:
                break
        return ComponentResult(component=self.name, results=tuple(results))
