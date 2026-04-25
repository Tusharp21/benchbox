"""`benchbox quickstart` — one prompt-set, one confirm, full provision-to-site flow.

Designed for the `curl | bash` install path where the user runs install.sh,
gets a `benchbox` shim, and wants a Frappe-ready dev environment with a
working bench + site at the end. We collect every input upfront, show a
plan, ask one yes/no, then run end-to-end with no further prompts. On
success we print the bench dir and a per-step success table; on failure
we print the same table with the failed step marked, so the user can see
how far we got.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

import typer
from benchbox_core import bench as core_bench
from benchbox_core import credentials, detect, discovery, preflight
from benchbox_core import site as core_site
from benchbox_core.installer import (
    AptComponent,
    BenchCliComponent,
    CommandRunner,
    MariaDBComponent,
    NodeComponent,
    RedisComponent,
    WkhtmltopdfComponent,
    install,
)
from rich.panel import Panel
from rich.table import Table

from benchbox_cli._output import (
    console,
    err_console,
    print_install_result,
    print_preflight,
)

quickstart_app = typer.Typer(help="provision Frappe + create your first bench and site in one shot")

DEFAULT_BENCH_PATH: Path = Path.home() / "frappe-bench"
DEFAULT_SITE_NAME: str = "site1.local"


@dataclass
class _StepRow:
    name: str
    ok: bool
    note: str = ""


def _prompt_password(label: str) -> str:
    first = getpass(f"  {label}: ")
    second = getpass("  Confirm: ")
    if first != second:
        err_console.print("[red]passwords do not match[/]")
        raise typer.Exit(2)
    if not first:
        err_console.print("[red]password cannot be empty[/]")
        raise typer.Exit(2)
    return first


def _print_summary(rows: list[_StepRow], *, bench_path: Path | None, site_name: str | None) -> None:
    table = Table(title="quickstart summary", header_style="bold", show_lines=False)
    table.add_column("step")
    table.add_column("state")
    table.add_column("note", overflow="fold")
    for row in rows:
        state = "[green]✓ success[/]" if row.ok else "[red]✗ failed[/]"
        table.add_row(row.name, state, row.note)
    console.print(table)

    if all(row.ok for row in rows) and bench_path is not None and site_name is not None:
        console.print(
            Panel.fit(
                f"[green bold]✓ ready[/]\n"
                f"  bench dir : {bench_path}\n"
                f"  site      : {site_name}\n\n"
                f"  start dev server : cd {bench_path} && bench start\n"
                f"  open in browser  : http://{site_name}:8000  (after `bench start`)",
                border_style="green",
            )
        )
    else:
        err_console.print(
            "[yellow]quickstart did not finish cleanly. "
            "Steps marked ✗ above are what failed; the rest succeeded.[/]"
        )


@quickstart_app.callback(invoke_without_command=True)
def main(
    skip_preflight: bool = typer.Option(
        False, "--skip-preflight", help="skip RAM/disk/port readiness checks"
    ),
) -> None:
    """Interactive one-shot: ask everything upfront, then run end-to-end."""
    try:
        os_info = detect.detect_os()
        detect.require_supported(os_info)
    except detect.UnsupportedOSError as err:
        err_console.print(f"[red bold]unsupported host:[/] {err}")
        raise typer.Exit(2) from err

    console.print(
        Panel.fit(
            "[bold cyan]benchbox quickstart[/]\n"
            f"host: {os_info.pretty_name} ({os_info.arch})\n\n"
            "I will:\n"
            "  1. Run preflight checks (RAM / disk / ports / internet / sudo)\n"
            "  2. Install: apt deps · MariaDB · Redis · Node (via nvm) · "
            "wkhtmltopdf · bench-cli\n"
            "  3. Create your first bench (bench init)\n"
            "  4. Create your first site (bench new-site)\n\n"
            "I will ask everything I need now, then run end-to-end with no "
            "further prompts.",
            border_style="cyan",
        )
    )

    # --- collect every input upfront --------------------------------
    bench_path_str = typer.prompt("Bench path", default=str(DEFAULT_BENCH_PATH))
    bench_path = Path(bench_path_str).expanduser().resolve()
    if bench_path.exists():
        if discovery.is_bench(bench_path):
            err_console.print(f"[red]{bench_path} already contains a Frappe bench[/]")
        else:
            err_console.print(
                f"[red]{bench_path} already exists.[/] "
                "bench init won't populate an existing dir — pick a path that doesn't exist yet."
            )
        raise typer.Exit(2)

    frappe_branch = typer.prompt("Frappe branch", default=core_bench.DEFAULT_FRAPPE_BRANCH)
    site_name = typer.prompt("First site name", default=DEFAULT_SITE_NAME)

    saved_pw = credentials.get_mariadb_root_password()
    if saved_pw is not None:
        console.print("[dim]Using stored MariaDB root password from ~/.benchbox/credentials.json[/]")
        mariadb_pw = saved_pw
    else:
        console.print(
            "[bold]MariaDB root password[/] "
            "[dim](will be saved 0600 to ~/.benchbox/credentials.json):[/]"
        )
        mariadb_pw = _prompt_password("Choose MariaDB root password")

    console.print("[bold]Site Administrator password:[/]")
    admin_pw = _prompt_password("Choose Administrator password")

    # --- show plan + single confirm ---------------------------------
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Host", f"{os_info.pretty_name} ({os_info.arch})")
    summary.add_row("Bench path", str(bench_path))
    summary.add_row("Frappe branch", frappe_branch)
    summary.add_row("First site", site_name)
    console.print(Panel(summary, title="will provision", border_style="green"))

    if not typer.confirm("Proceed?", default=True):
        console.print("[yellow]aborted — nothing changed.[/]")
        raise typer.Exit(0)

    # Persist the MariaDB password now so any later step that asks
    # `credentials.get_mariadb_root_password()` finds it.
    if saved_pw is None:
        credentials.set_mariadb_root_password(mariadb_pw)

    rows: list[_StepRow] = []

    # --- preflight --------------------------------------------------
    if not skip_preflight:
        report = preflight.run_preflight()
        print_preflight(report)
        if not report.passed:
            rows.append(
                _StepRow(
                    name="preflight",
                    ok=False,
                    note="failed checks above; re-run with --skip-preflight to proceed anyway",
                )
            )
            _print_summary(rows, bench_path=None, site_name=None)
            raise typer.Exit(1)
        rows.append(_StepRow(name="preflight", ok=True))

    # --- install components ----------------------------------------
    components = [
        AptComponent(),
        MariaDBComponent(root_password=mariadb_pw),
        RedisComponent(),
        NodeComponent(),
        WkhtmltopdfComponent(
            ubuntu_version=os_info.version_id,
            machine_arch=platform.machine(),
        ),
        BenchCliComponent(),
    ]
    runner = CommandRunner(dry_run=False)
    install_result = install(components, runner=runner)
    print_install_result(install_result)

    for component in install_result.components:
        rows.append(
            _StepRow(
                name=f"install · {component.component}",
                ok=component.ok,
                note="" if component.ok else "see component table above",
            )
        )

    if not install_result.ok:
        _print_summary(rows, bench_path=None, site_name=None)
        raise typer.Exit(1)

    # --- bench init -------------------------------------------------
    try:
        core_bench.create_bench(bench_path, frappe_branch=frappe_branch, runner=runner)
    except core_bench.BenchAlreadyExistsError as err:
        rows.append(_StepRow(name=f"bench at {bench_path}", ok=False, note=str(err)))
        _print_summary(rows, bench_path=None, site_name=None)
        raise typer.Exit(1) from err
    except core_bench.BenchCreationError as err:
        rows.append(_StepRow(name=f"bench at {bench_path}", ok=False, note=str(err)))
        _print_summary(rows, bench_path=None, site_name=None)
        raise typer.Exit(1) from err
    rows.append(_StepRow(name=f"bench at {bench_path}", ok=True))

    # --- new-site ---------------------------------------------------
    try:
        core_site.create_site(
            bench_path,
            site_name,
            db_root_password=mariadb_pw,
            admin_password=admin_pw,
            runner=runner,
        )
    except (core_site.SiteAlreadyExistsError, core_site.SiteOperationError) as err:
        rows.append(_StepRow(name=f"site {site_name}", ok=False, note=str(err)))
        _print_summary(rows, bench_path=bench_path, site_name=None)
        raise typer.Exit(1) from err
    rows.append(_StepRow(name=f"site {site_name}", ok=True))

    _print_summary(rows, bench_path=bench_path, site_name=site_name)
