"""`benchbox bench` — bench lifecycle (new / list / info)."""

from __future__ import annotations

from pathlib import Path

import typer
from benchbox_core import bench as core_bench
from benchbox_core import discovery, introspect
from benchbox_core.installer import CommandRunner
from rich.table import Table

from benchbox_cli._output import console, err_console, print_bench_info

bench_app = typer.Typer(help="create, list, and inspect Frappe benches")


@bench_app.command("new")
def new_cmd(
    path: Path = typer.Argument(..., help="where the new bench dir will be created"),
    frappe_branch: str = typer.Option(
        core_bench.DEFAULT_FRAPPE_BRANCH,
        "--frappe-branch",
        help="the Frappe git branch to init (default: version-15)",
    ),
    python_bin: str = typer.Option(
        core_bench.DEFAULT_PYTHON_BIN, "--python", help="python interpreter for the bench env"
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Create a new Frappe bench at PATH via `bench init`."""
    runner = CommandRunner(dry_run=dry_run)
    try:
        result = core_bench.create_bench(
            path, frappe_branch=frappe_branch, python_bin=python_bin, runner=runner
        )
    except core_bench.BenchAlreadyExistsError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(2) from err
    except core_bench.BenchCreationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if result.info is not None:
        console.print("[green bold]✓ bench ready[/]")
        print_bench_info(result.info)
    else:
        console.print("[yellow]dry-run: nothing executed[/]")


@bench_app.command("list")
def list_cmd(
    root: Path = typer.Option(
        Path.home(),
        "--root",
        help="directory to scan for benches",
        dir_okay=True,
        file_okay=False,
        exists=True,
    ),
    depth: int = typer.Option(discovery.DEFAULT_MAX_DEPTH, "--depth"),
) -> None:
    """List every bench under ROOT."""
    paths = discovery.discover_benches(search_paths=[root], max_depth=depth)
    if not paths:
        console.print(f"[dim]no benches found under {root}[/]")
        return

    table = Table(title="benches", show_header=True, header_style="bold")
    table.add_column("path")
    table.add_column("frappe")
    table.add_column("python")
    table.add_column("sites", justify="right")
    table.add_column("apps", justify="right")
    for path in paths:
        info = introspect.introspect(path)
        table.add_row(
            str(info.path),
            info.frappe_version or "-",
            info.python_version or "-",
            str(len(info.sites)),
            str(len(info.apps)),
        )
    console.print(table)


@bench_app.command("info")
def info_cmd(
    path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
) -> None:
    """Show detailed info about a single bench."""
    if not discovery.is_bench(path):
        err_console.print(f"[red]not a bench directory:[/] {path}")
        raise typer.Exit(2)
    print_bench_info(introspect.introspect(path))
