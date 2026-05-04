"""apt component: base system packages Frappe needs."""

from __future__ import annotations

from dataclasses import dataclass, field

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)

BASE_PACKAGES: tuple[str, ...] = (
    "git",
    "curl",
    "wget",
    "ca-certificates",
    "build-essential",
    "pkg-config",
    "python3-dev",
    "python3-venv",
    "python3-pip",
    "python3-setuptools",
    "libffi-dev",
    "libssl-dev",
    "libmariadb-dev",
    "libjpeg-dev",
    "zlib1g-dev",
    "software-properties-common",
    "fontconfig",
    "xvfb",
    "libxrender1",
    "libxext6",
    "xfonts-75dpi",
    "xfonts-base",
)


def _dpkg_installed(runner: CommandRunner, package: str) -> bool:
    result = runner.run(
        ["dpkg-query", "-W", "-f=${Status}", package],
        check=False,
    )
    if not result.executed:
        return False
    if result.returncode != 0:
        return False
    return result.stdout.strip() == "install ok installed"


@dataclass
class AptComponent:
    name: str = field(default="apt", init=False)
    packages: tuple[str, ...] = BASE_PACKAGES
    probe_runner: CommandRunner = field(default_factory=lambda: CommandRunner(quiet=True))
    use_sudo: bool = True

    def _sudo(self, argv: list[str]) -> tuple[str, ...]:
        return tuple(["sudo", *argv]) if self.use_sudo else tuple(argv)

    def _missing_packages(self) -> tuple[str, ...]:
        return tuple(p for p in self.packages if not _dpkg_installed(self.probe_runner, p))

    def plan(self) -> ComponentPlan:
        missing = self._missing_packages()
        steps: list[Step] = []

        if not missing:
            steps.append(
                Step(
                    description="all base packages already installed",
                    command=(),
                    skip_reason="nothing to install",
                )
            )
            return ComponentPlan(component=self.name, steps=tuple(steps))

        steps.append(
            Step(
                description="apt-get update",
                command=self._sudo(["apt-get", "update"]),
            )
        )
        steps.append(
            Step(
                description=f"install {len(missing)} package(s): {', '.join(missing)}",
                command=self._sudo(
                    ["apt-get", "install", "-y", "--no-install-recommends", *missing]
                ),
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
            results.append(
                StepResult(
                    step=step,
                    executed=cmd_result.executed,
                    skipped=False,
                    returncode=cmd_result.returncode,
                    error=cmd_result.stderr.strip() or None
                    if cmd_result.executed and cmd_result.returncode != 0
                    else None,
                )
            )
            if cmd_result.executed and cmd_result.returncode != 0:
                break
        return ComponentResult(component=self.name, results=tuple(results))
