"""Redis component — install redis-server, enable + start the service.

Scope is intentionally narrow: apt install plus service management. Frappe's
own bench spawns per-bench redis-cache / redis-queue / redis-socketio on
private ports via the Procfile, so the system redis-server on 6379 isn't
strictly required at runtime — but Frappe's install docs enable it, and
having the ``redis-cli`` / ``redis-server`` binaries present is what bench
needs in order to spawn its own processes.
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

REDIS_PACKAGE: str = "redis-server"
REDIS_SERVICE: str = "redis-server"


def _dpkg_installed(runner: CommandRunner, package: str) -> bool:
    result = runner.run(["dpkg-query", "-W", "-f=${Status}", package], check=False)
    if not result.executed or result.returncode != 0:
        return False
    return result.stdout.strip() == "install ok installed"


def _service_active(runner: CommandRunner, service: str) -> bool:
    result = runner.run(["systemctl", "is-active", "--quiet", service], check=False)
    return result.executed and result.returncode == 0


@dataclass
class RedisComponent:
    """Install and enable system redis-server."""

    name: str = field(default="redis", init=False)
    probe_runner: CommandRunner = field(default_factory=CommandRunner)
    use_sudo: bool = True

    def _sudo(self, argv: list[str]) -> tuple[str, ...]:
        return tuple(["sudo", *argv]) if self.use_sudo else tuple(argv)

    def plan(self) -> ComponentPlan:
        steps: list[Step] = []
        installed = _dpkg_installed(self.probe_runner, REDIS_PACKAGE)

        if installed:
            steps.append(
                Step(
                    description=f"{REDIS_PACKAGE} already installed",
                    command=(),
                    skip_reason="package present",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"install {REDIS_PACKAGE}",
                    command=self._sudo(
                        [
                            "apt-get",
                            "install",
                            "-y",
                            "--no-install-recommends",
                            REDIS_PACKAGE,
                        ]
                    ),
                )
            )

        steps.append(
            Step(
                description=f"enable {REDIS_SERVICE} on boot",
                command=self._sudo(["systemctl", "enable", REDIS_SERVICE]),
            )
        )

        if _service_active(self.probe_runner, REDIS_SERVICE):
            steps.append(
                Step(
                    description=f"{REDIS_SERVICE} already running",
                    command=(),
                    skip_reason="service active",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"start {REDIS_SERVICE}",
                    command=self._sudo(["systemctl", "start", REDIS_SERVICE]),
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
