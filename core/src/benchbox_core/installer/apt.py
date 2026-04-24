"""apt component — base system packages Frappe needs to build and run.

The scope here is *only* the packages Frappe itself needs from Ubuntu's
archive (build toolchain, Python headers, libffi/libssl/libmariadb dev
headers, fontconfig for wkhtmltopdf). Server packages like MariaDB and Redis
are owned by their own components so they can manage config + services.

The component is idempotent: ``plan()`` queries ``dpkg-query`` for each
package's install state and emits ``skip_reason`` for anything already
present, so re-running ``apply()`` on a fully-provisioned host is a no-op.
"""

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
    "libxrender1",
    "libxext6",
    "xfonts-75dpi",
    "xfonts-base",
)


def _dpkg_installed(runner: CommandRunner, package: str) -> bool:
    """Return True iff ``dpkg-query`` reports ``package`` as install-ok installed."""
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
    """Install base build/runtime deps from the Ubuntu archive.

    ``packages`` is exposed so tests (and, later, bench-profile configs) can
    narrow or extend the default set without monkey-patching the module.

    The ``probe_runner`` is used to *ask dpkg* which packages are already
    installed. It is almost always a dry-run-disabled runner (probing needs
    real output); the runner passed to ``apply()`` can be dry-run to show the
    planned commands without executing them.
    """

    name: str = field(default="apt", init=False)
    packages: tuple[str, ...] = BASE_PACKAGES
    probe_runner: CommandRunner = field(default_factory=CommandRunner)
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
