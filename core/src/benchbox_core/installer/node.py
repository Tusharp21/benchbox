"""Node component — per-user nvm + Node 18."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)

# Pinned so an upstream nvm release can't silently change what we install.
# Bump deliberately when upstream has a meaningful fix.
NVM_VERSION: str = "v0.39.7"
NVM_INSTALL_URL: str = f"https://raw.githubusercontent.com/nvm-sh/nvm/{NVM_VERSION}/install.sh"

# Frappe v15 requires Node 18+. Default to 18 LTS until Frappe bumps again.
DEFAULT_NODE_MAJOR: str = "18"


@dataclass
class NodeComponent:

    name: str = field(default="node", init=False)
    node_major: str = DEFAULT_NODE_MAJOR
    install_yarn: bool = True
    nvm_dir: Path = field(default_factory=lambda: Path.home() / ".nvm")
    nvm_install_url: str = NVM_INSTALL_URL

    # --- probes --------------------------------------------------------

    def _nvm_installed(self) -> bool:
        return (self.nvm_dir / "nvm.sh").is_file()

    def _node_installed(self) -> bool:
        versions_dir = self.nvm_dir / "versions" / "node"
        if not versions_dir.is_dir():
            return False
        prefix = f"v{self.node_major}."
        return any(child.name.startswith(prefix) for child in versions_dir.iterdir())

    def _yarn_installed(self) -> bool:
        versions_dir = self.nvm_dir / "versions" / "node"
        if not versions_dir.is_dir():
            return False
        return any((node_dir / "bin" / "yarn").exists() for node_dir in versions_dir.iterdir())

    # --- plan ----------------------------------------------------------

    def _nvm_source_snippet(self) -> str:
        return f'export NVM_DIR={shlex.quote(str(self.nvm_dir))} && . "$NVM_DIR/nvm.sh"'

    def _bash_login_command(self, script: str) -> tuple[str, ...]:
        # ``-l`` gives us a login shell so ~/.profile (which nvm's installer
        # writes to) is sourced; ``-c`` runs our snippet.
        return ("bash", "-lc", script)

    def plan(self) -> ComponentPlan:
        steps: list[Step] = []

        if self._nvm_installed():
            steps.append(
                Step(
                    description=f"nvm already installed at {self.nvm_dir}",
                    command=(),
                    skip_reason="nvm present",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"install nvm {NVM_VERSION}",
                    command=self._bash_login_command(
                        f"curl -fsSL {shlex.quote(self.nvm_install_url)} | bash"
                    ),
                )
            )

        if self._node_installed():
            steps.append(
                Step(
                    description=f"Node {self.node_major} already installed via nvm",
                    command=(),
                    skip_reason=f"node v{self.node_major}.x present",
                )
            )
        else:
            node_script = (
                f"{self._nvm_source_snippet()} && nvm install {shlex.quote(self.node_major)}"
            )
            steps.append(
                Step(
                    description=f"install Node {self.node_major} via nvm",
                    command=self._bash_login_command(node_script),
                )
            )

        if self.install_yarn:
            if self._yarn_installed():
                steps.append(
                    Step(
                        description="yarn already installed",
                        command=(),
                        skip_reason="yarn present",
                    )
                )
            else:
                steps.append(
                    Step(
                        description="install yarn globally via npm",
                        command=self._bash_login_command(
                            f"{self._nvm_source_snippet()}"
                            f" && nvm use {shlex.quote(self.node_major)}"
                            " && npm install -g yarn"
                        ),
                    )
                )

        return ComponentPlan(component=self.name, steps=tuple(steps))

    # --- apply ---------------------------------------------------------

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
