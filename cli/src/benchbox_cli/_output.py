"""Shared Rich-based output helpers for the CLI.

Kept in one place so the formatting of a ``ComponentPlan`` in ``benchbox
install --dry-run`` looks the same as when the plan is printed before an
actual run. Same story for bench/site/app info tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

_GB: int = 1024**3

if TYPE_CHECKING:
    from benchbox_core.installer import ComponentPlan, ComponentResult, InstallResult
    from benchbox_core.introspect import BenchInfo
    from benchbox_core.preflight import PreflightReport
    from benchbox_core.stats import SystemStats


console = Console()
err_console = Console(stderr=True)


def _status_mark(ok: bool) -> str:
    return "[green]✓[/]" if ok else "[red]✗[/]"


def print_plan(plan: ComponentPlan) -> None:
    table = Table(title=f"[bold]{plan.component}[/]", show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("step")
    table.add_column("skip reason", style="yellow")
    for i, step in enumerate(plan.steps, 1):
        table.add_row(str(i), step.description, step.skip_reason or "")
    console.print(table)


def print_component_result(result: ComponentResult) -> None:
    table = Table(
        title=f"{_status_mark(result.ok)} [bold]{result.component}[/]",
        show_header=True,
        header_style="bold",
    )
    table.add_column("step")
    table.add_column("state")
    table.add_column("details", overflow="fold")
    for r in result.results:
        if r.skipped:
            state = "[dim]skipped[/]"
            details = r.step.skip_reason or ""
        elif not r.executed:
            state = "[dim]dry-run[/]"
            details = ""
        elif r.ok:
            state = "[green]ok[/]"
            details = ""
        else:
            state = "[red]failed[/]"
            details = r.error or f"exit {r.returncode}"
        table.add_row(r.step.description, state, details)
    console.print(table)


def print_install_result(result: InstallResult) -> None:
    for component in result.components:
        print_component_result(component)
    if result.ok:
        console.print("[green bold]✓ install complete[/]")
    else:
        failed = result.failed_component
        name = failed.component if failed else "?"
        err_console.print(f"[red bold]✗ install failed at {name}[/]")


def print_preflight(report: PreflightReport) -> None:
    table = Table(title="[bold]preflight[/]", show_header=True, header_style="bold")
    table.add_column("check")
    table.add_column("state")
    table.add_column("details", overflow="fold")
    for c in report.checks:
        table.add_row(c.name, _status_mark(c.passed), c.message)
    console.print(table)


def print_bench_info(info: BenchInfo) -> None:
    header = Table.grid(padding=(0, 2))
    header.add_column(style="bold")
    header.add_column()
    header.add_row("path", str(info.path))
    header.add_row("frappe version", info.frappe_version or "-")
    header.add_row("python", info.python_version or "-")
    header.add_row("git branch", info.git_branch or "-")
    console.print(header)

    apps = Table(title="apps", show_header=True, header_style="bold")
    apps.add_column("name")
    apps.add_column("version")
    apps.add_column("branch")
    for app in info.apps:
        apps.add_row(app.name, app.version or "-", app.git_branch or "-")
    console.print(apps)

    sites = Table(title="sites", show_header=True, header_style="bold")
    sites.add_column("name")
    sites.add_column("db name")
    sites.add_column("apps")
    for site in info.sites:
        sites.add_row(
            site.name,
            site.db_name or "-",
            ", ".join(site.installed_apps) if site.installed_apps else "-",
        )
    console.print(sites)


def print_stats(snapshot: SystemStats) -> None:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    grid.add_row("cpu", f"{snapshot.cpu_percent:.1f}%")
    ram_total = snapshot.memory.total_bytes / _GB
    ram_used = snapshot.memory.used_bytes / _GB
    grid.add_row(
        "ram",
        f"{ram_used:.1f} / {ram_total:.1f} GB ({snapshot.memory.percent:.1f}%)",
    )
    disk_total = snapshot.disk.total_bytes / _GB
    disk_used = (snapshot.disk.total_bytes - snapshot.disk.free_bytes) / _GB
    grid.add_row(
        "disk",
        f"{disk_used:.1f} / {disk_total:.1f} GB ({snapshot.disk.percent:.1f}%) "
        f"[dim]at {snapshot.disk.path}[/]",
    )
    console.print(grid)

    services = Table(title="services", show_header=True, header_style="bold")
    services.add_column("service")
    services.add_column("state")
    for svc in snapshot.services:
        color = "green" if svc.active else "red"
        services.add_row(svc.name, f"[{color}]{svc.state}[/]")
    console.print(services)
