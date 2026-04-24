"""`benchbox install` — one command to provision a Frappe-ready host.

Runs preflight, gates on distro + arch, resolves the MariaDB root password
(prompting once and persisting to the credentials store), then sequences
every installer component through the core ``install()`` orchestrator.
"""

from __future__ import annotations

import platform
from getpass import getpass

import typer
from benchbox_core import credentials, detect, preflight
from benchbox_core.installer import (
    AptComponent,
    BenchCliComponent,
    CommandRunner,
    Component,
    MariaDBComponent,
    NodeComponent,
    RedisComponent,
    WkhtmltopdfComponent,
    install,
)

from benchbox_cli._output import (
    console,
    err_console,
    print_install_result,
    print_plan,
    print_preflight,
)

install_app = typer.Typer(help="install benchbox's Frappe prerequisites on this host")


def _resolve_mariadb_password(*, assume_yes: bool) -> str:
    saved = credentials.get_mariadb_root_password()
    if saved is not None:
        return saved
    if assume_yes:
        raise typer.BadParameter(
            "--yes was passed but no MariaDB root password is stored; "
            "run once interactively or pre-populate ~/.benchbox/credentials.json"
        )
    console.print(
        "[bold]MariaDB root password not yet configured.[/] "
        "benchbox will set this on the new install (or use it to talk to an "
        "existing MariaDB). It's stored at [dim]~/.benchbox/credentials.json[/] "
        "with 0600 perms."
    )
    first = getpass("Choose MariaDB root password: ")
    second = getpass("Confirm: ")
    if first != second:
        raise typer.BadParameter("passwords do not match")
    if not first:
        raise typer.BadParameter("password cannot be empty")
    credentials.set_mariadb_root_password(first)
    return first


def _build_components(*, os_info: detect.OSInfo, mariadb_password: str) -> list[Component]:
    # Order matters: apt first (brings pipx/curl/etc.), then services, then
    # wkhtmltopdf (wants fontconfig present), then bench CLI (needs pipx).
    return [
        AptComponent(),
        MariaDBComponent(root_password=mariadb_password),
        RedisComponent(),
        NodeComponent(),
        WkhtmltopdfComponent(
            ubuntu_version=os_info.version_id,
            machine_arch=platform.machine(),
        ),
        BenchCliComponent(),
    ]


@install_app.callback(invoke_without_command=True)
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="print the plan, don't touch the system"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="don't prompt; require credentials to already be stored",
    ),
    skip_preflight: bool = typer.Option(
        False, "--skip-preflight", help="skip RAM/disk/port readiness checks"
    ),
) -> None:
    """Install system prereqs + the bench CLI in one shot."""
    try:
        os_info = detect.detect_os()
        detect.require_supported(os_info)
    except detect.UnsupportedOSError as err:
        err_console.print(f"[red bold]unsupported host:[/] {err}")
        raise typer.Exit(2) from err
    console.print(f"[dim]host:[/] {os_info.pretty_name} ({os_info.arch})")

    if not skip_preflight:
        report = preflight.run_preflight()
        print_preflight(report)
        if not report.passed:
            err_console.print(
                "[yellow]preflight has failures; use --skip-preflight to proceed anyway[/]"
            )
            raise typer.Exit(1)

    mariadb_password = _resolve_mariadb_password(assume_yes=yes)
    components = _build_components(os_info=os_info, mariadb_password=mariadb_password)

    if dry_run:
        for component in components:
            print_plan(component.plan())
        console.print("[yellow]dry-run: nothing executed[/]")
        return

    result = install(components, runner=CommandRunner(dry_run=False))
    print_install_result(result)
    if not result.ok:
        raise typer.Exit(1)
