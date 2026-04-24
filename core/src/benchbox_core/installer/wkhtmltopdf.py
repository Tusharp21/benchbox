"""wkhtmltopdf component — patched-qt build for Frappe print formats.

Frappe needs the *patched-qt* wkhtmltopdf build (the unpatched Ubuntu
archive package renders print formats with subtly broken fonts and
margins). We download the ``.deb`` from the upstream ``wkhtmltopdf/packaging``
GitHub release and install it through apt so transitive deps get resolved
automatically.

Three plan shapes, selected by probing ``wkhtmltopdf --version``:
    - missing → download + install patched .deb
    - patched → skip (everything is already how we want it)
    - unpatched → purge + download + install; the purge step is explicit in
      the plan so the user sees why we're touching a working binary

Ubuntu 24.04 (``noble``) uses the ``jammy`` .deb because upstream packaging
hasn't shipped a noble build; the jammy binary runs fine on noble's libs.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

from benchbox_core.installer._run import CommandRunner
from benchbox_core.installer._types import (
    ComponentPlan,
    ComponentResult,
    Step,
    StepResult,
)

WKHTMLTOPDF_VERSION: str = "0.12.6.1-3"
PATCHED_QT_MARKER: str = "with patched qt"
UPSTREAM_PACKAGE: str = "wkhtmltox"  # upstream .deb name (vs Ubuntu's "wkhtmltopdf")
UBUNTU_PACKAGE: str = "wkhtmltopdf"  # what the unpatched Ubuntu archive ships as


class UnsupportedWkhtmltopdfPlatform(RuntimeError):
    """Raised when the current OS/arch isn't one we have a patched build for."""


def _codename_for(ubuntu_version: str) -> str:
    # Upstream packaging only ships jammy + focal + bullseye builds for this
    # release. 24.04 noble uses the jammy build (libs are ABI-compatible).
    if ubuntu_version in {"22.04", "24.04"}:
        return "jammy"
    raise UnsupportedWkhtmltopdfPlatform(
        f"no patched-qt wkhtmltopdf build available for Ubuntu {ubuntu_version}"
    )


def _deb_arch_for(machine_arch: str) -> str:
    if machine_arch == "x86_64":
        return "amd64"
    if machine_arch == "aarch64":
        return "arm64"
    raise UnsupportedWkhtmltopdfPlatform(
        f"no patched-qt wkhtmltopdf build for architecture {machine_arch}"
    )


def deb_filename(ubuntu_version: str, machine_arch: str) -> str:
    codename = _codename_for(ubuntu_version)
    arch = _deb_arch_for(machine_arch)
    return f"wkhtmltox_{WKHTMLTOPDF_VERSION}.{codename}_{arch}.deb"


def deb_url(ubuntu_version: str, machine_arch: str) -> str:
    filename = deb_filename(ubuntu_version, machine_arch)
    return (
        "https://github.com/wkhtmltopdf/packaging/releases/download/"
        f"{WKHTMLTOPDF_VERSION}/{filename}"
    )


@dataclass(frozen=True)
class WkhtmltopdfProbeResult:
    """Outcome of probing the system for an existing wkhtmltopdf."""

    installed: bool
    patched: bool
    raw_version: str | None


def probe_wkhtmltopdf(runner: CommandRunner) -> WkhtmltopdfProbeResult:
    """Run ``wkhtmltopdf --version`` and interpret the output."""
    result = runner.run(["wkhtmltopdf", "--version"], check=False)
    if not result.executed or result.returncode != 0:
        return WkhtmltopdfProbeResult(installed=False, patched=False, raw_version=None)
    version_line = result.stdout.strip() or result.stderr.strip()
    patched = PATCHED_QT_MARKER in version_line.lower()
    return WkhtmltopdfProbeResult(installed=True, patched=patched, raw_version=version_line or None)


@dataclass
class WkhtmltopdfComponent:
    """Install the patched-qt wkhtmltopdf build for Frappe print formats."""

    name: str = field(default="wkhtmltopdf", init=False)
    ubuntu_version: str = ""  # e.g. "22.04"; empty means detect at plan time
    machine_arch: str = ""  # e.g. "x86_64"; empty means detect at plan time
    download_dir: Path = Path("/tmp")
    probe_runner: CommandRunner = field(default_factory=CommandRunner)
    use_sudo: bool = True

    def _sudo(self, argv: list[str]) -> tuple[str, ...]:
        return tuple(["sudo", *argv]) if self.use_sudo else tuple(argv)

    def _resolve_target(self) -> tuple[str, str]:
        version = self.ubuntu_version
        arch = self.machine_arch
        if not arch:
            arch = platform.machine()
        # ubuntu_version must be supplied by the caller (detect.OSInfo) — we
        # don't re-read /etc/os-release here to keep this module side-effect-free.
        if not version:
            raise UnsupportedWkhtmltopdfPlatform(
                "ubuntu_version must be set before calling plan(); "
                "pass detect.detect_os().version_id"
            )
        return version, arch

    def plan(self) -> ComponentPlan:
        version, arch = self._resolve_target()
        filename = deb_filename(version, arch)
        url = deb_url(version, arch)
        local_deb = self.download_dir / filename

        probe = probe_wkhtmltopdf(self.probe_runner)

        if probe.installed and probe.patched:
            return ComponentPlan(
                component=self.name,
                steps=(
                    Step(
                        description="patched-qt wkhtmltopdf already installed",
                        command=(),
                        skip_reason="patched build present",
                    ),
                ),
            )

        steps: list[Step] = []

        if probe.installed and not probe.patched:
            # Purge the unpatched Ubuntu package before we install the upstream
            # .deb, so there's no ambiguity about which binary wins on PATH.
            steps.append(
                Step(
                    description=(
                        f"purge unpatched wkhtmltopdf "
                        f"(detected: {probe.raw_version or 'unknown version'})"
                    ),
                    command=self._sudo(["apt-get", "purge", "-y", UBUNTU_PACKAGE]),
                )
            )

        steps.append(
            Step(
                description=f"download patched-qt wkhtmltopdf {WKHTMLTOPDF_VERSION}",
                command=(
                    "curl",
                    "-fsSL",
                    "--output",
                    str(local_deb),
                    url,
                ),
            )
        )
        steps.append(
            Step(
                description=f"install {filename}",
                command=self._sudo(
                    ["apt-get", "install", "-y", "--no-install-recommends", str(local_deb)]
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
