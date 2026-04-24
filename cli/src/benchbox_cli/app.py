"""`benchbox app` — app lifecycle (get / install / uninstall)."""

from __future__ import annotations

from pathlib import Path

import typer
from benchbox_core import app as core_app
from benchbox_core.installer import CommandRunner

from benchbox_cli._output import console, err_console

app_cli = typer.Typer(help="download apps into a bench and manage their site installs")


@app_cli.command("get")
def get_cmd(
    bench_path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
    git_url: str = typer.Argument(..., help="git URL of the app"),
    branch: str | None = typer.Option(None, "--branch"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    skip_assets: bool = typer.Option(False, "--skip-assets"),
    resolve_deps: bool = typer.Option(False, "--resolve-deps"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Download an app into the bench via `bench get-app`."""
    runner = CommandRunner(dry_run=dry_run)
    try:
        result = core_app.get_app(
            bench_path,
            git_url,
            branch=branch,
            overwrite=overwrite,
            skip_assets=skip_assets,
            resolve_deps=resolve_deps,
            runner=runner,
        )
    except core_app.AppOperationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if dry_run:
        console.print("[yellow]dry-run: nothing executed[/]")
        return
    names = ", ".join(a.name for a in result.apps) or "-"
    console.print(f"[green]✓ app fetched[/] (apps now present: {names})")


@app_cli.command("install")
def install_cmd(
    bench_path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
    site: str = typer.Argument(...),
    apps: list[str] = typer.Argument(..., help="one or more app names to install"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Install one or more apps onto SITE."""
    runner = CommandRunner(dry_run=dry_run)
    try:
        core_app.install_app(bench_path, site, apps, force=force, runner=runner)
    except core_app.AppOperationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if dry_run:
        console.print("[yellow]dry-run: nothing executed[/]")
    else:
        console.print(f"[green]✓ installed {', '.join(apps)} on {site}[/]")


@app_cli.command("uninstall")
def uninstall_cmd(
    bench_path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
    site: str = typer.Argument(...),
    app: str = typer.Argument(...),
    no_backup: bool = typer.Option(False, "--no-backup"),
    force: bool = typer.Option(False, "--force"),
    yes: bool = typer.Option(True, "--yes/--ask"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Uninstall APP from SITE."""
    runner = CommandRunner(dry_run=dry_run)
    try:
        core_app.uninstall_app(
            bench_path,
            site,
            app,
            yes=yes,
            no_backup=no_backup,
            force=force,
            runner=runner,
        )
    except core_app.AppOperationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if dry_run:
        console.print("[yellow]dry-run: nothing executed[/]")
    else:
        console.print(f"[green]✓ uninstalled {app} from {site}[/]")
