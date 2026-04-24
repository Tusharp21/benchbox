"""MariaDB component — install server, apply Frappe charset, set root password.

Responsibility boundary: this component installs the ``mariadb-server``
package, drops a Frappe-compatible config override into
``/etc/mysql/mariadb.conf.d/``, ensures the service is enabled + running,
and sets the DB root password to whatever was saved in the credentials
store. Prompting the user for the password is owned by the CLI / GUI, not
by core.

Idempotency: each concern (package, config override, service, password) is
probed independently, so a component that has already run emits only the
steps whose state has drifted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)

MARIADB_PACKAGE: str = "mariadb-server"
CONFIG_OVERRIDE_PATH: Path = Path("/etc/mysql/mariadb.conf.d/99-benchbox-frappe.cnf")
CONFIG_OVERRIDE_MARKER: str = "# benchbox-managed: do not edit by hand"
CONFIG_OVERRIDE_CONTENT: str = f"""{CONFIG_OVERRIDE_MARKER}
# Frappe requires utf8mb4 with unicode_ci collation for Unicode support
# across all text fields. Scope is mysqld + client + mysqldump so that
# ad-hoc dumps round-trip cleanly.

[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4

[mysqldump]
default-character-set = utf8mb4
"""


def _dpkg_installed(runner: CommandRunner, package: str) -> bool:
    result = runner.run(["dpkg-query", "-W", "-f=${Status}", package], check=False)
    if not result.executed or result.returncode != 0:
        return False
    return result.stdout.strip() == "install ok installed"


def _service_active(runner: CommandRunner, service: str) -> bool:
    result = runner.run(["systemctl", "is-active", "--quiet", service], check=False)
    return result.executed and result.returncode == 0


def _config_override_present(path: Path = CONFIG_OVERRIDE_PATH) -> bool:
    if not path.is_file():
        return False
    try:
        return CONFIG_OVERRIDE_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


@dataclass
class MariaDBComponent:
    """Install + configure MariaDB for Frappe local dev.

    ``root_password`` must be supplied by the caller (CLI/GUI) — the component
    does no prompting. When MariaDB is already installed from a prior setup,
    the caller is expected to pass the existing password; the component will
    only run the ``ALTER USER`` step if the service was freshly installed
    during this apply (tracked via plan state, not by poking the DB).
    """

    name: str = field(default="mariadb", init=False)
    root_password: str = ""
    probe_runner: CommandRunner = field(default_factory=CommandRunner)
    use_sudo: bool = True
    config_override_path: Path = CONFIG_OVERRIDE_PATH

    def _sudo(self, argv: list[str]) -> tuple[str, ...]:
        return tuple(["sudo", *argv]) if self.use_sudo else tuple(argv)

    def _already_installed(self) -> bool:
        return _dpkg_installed(self.probe_runner, MARIADB_PACKAGE)

    def plan(self) -> ComponentPlan:
        steps: list[Step] = []
        installed = self._already_installed()

        if not installed:
            steps.append(
                Step(
                    description=f"install {MARIADB_PACKAGE}",
                    command=self._sudo(
                        [
                            "apt-get",
                            "install",
                            "-y",
                            "--no-install-recommends",
                            MARIADB_PACKAGE,
                        ]
                    ),
                )
            )
        else:
            steps.append(
                Step(
                    description=f"{MARIADB_PACKAGE} already installed",
                    command=(),
                    skip_reason="package present",
                )
            )

        if _config_override_present(self.config_override_path):
            steps.append(
                Step(
                    description=f"Frappe charset override already at {self.config_override_path}",
                    command=(),
                    skip_reason="config override present",
                )
            )
        else:
            steps.append(
                Step(
                    description=f"write Frappe charset override to {self.config_override_path}",
                    command=self._sudo(["tee", str(self.config_override_path)]),
                    stdin=CONFIG_OVERRIDE_CONTENT,
                )
            )

        steps.append(
            Step(
                description="enable mariadb service on boot",
                command=self._sudo(["systemctl", "enable", "mariadb"]),
            )
        )

        if _service_active(self.probe_runner, "mariadb"):
            steps.append(
                Step(
                    description="restart mariadb to pick up config",
                    command=self._sudo(["systemctl", "restart", "mariadb"]),
                )
            )
        else:
            steps.append(
                Step(
                    description="start mariadb",
                    command=self._sudo(["systemctl", "start", "mariadb"]),
                )
            )

        # Password set runs only when the server was not already installed at
        # plan time. For an existing install we trust the caller's stored
        # password and do not touch the DB. SQL goes via stdin so the
        # password never appears in argv / ps output.
        if not installed:
            steps.append(
                Step(
                    description="set MariaDB root password",
                    command=self._sudo(["mysql", "-u", "root"]),
                    stdin=self._alter_root_sql(),
                )
            )

        return ComponentPlan(component=self.name, steps=tuple(steps))

    def _alter_root_sql(self) -> str:
        # Single-quote the password and escape any embedded single quote by
        # doubling it (MariaDB's standard SQL string escape). Passwords with
        # backslashes are not specially handled — Frappe has the same
        # restriction.
        escaped = self.root_password.replace("'", "''")
        return f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{escaped}';\nFLUSH PRIVILEGES;\n"

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
