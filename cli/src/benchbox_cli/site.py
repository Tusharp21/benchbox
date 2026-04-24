"""`benchbox site` — site lifecycle (new / drop)."""

from __future__ import annotations

from getpass import getpass
from pathlib import Path

import typer
from benchbox_core import credentials
from benchbox_core import site as core_site
from benchbox_core.installer import CommandRunner

from benchbox_cli._output import console, err_console

site_app = typer.Typer(help="create and drop Frappe sites inside a bench")


def _require_mariadb_password(assume_yes: bool) -> str:
    saved = credentials.get_mariadb_root_password()
    if saved is not None:
        return saved
    if assume_yes:
        raise typer.BadParameter(
            "no MariaDB root password stored; run `benchbox install` interactively first"
        )
    console.print(
        "[bold]MariaDB root password not stored yet.[/] "
        "Saving it to [dim]~/.benchbox/credentials.json[/] (0600)."
    )
    pw = getpass("MariaDB root password: ")
    if not pw:
        raise typer.BadParameter("password cannot be empty")
    credentials.set_mariadb_root_password(pw)
    return pw


@site_app.command("new")
def new_cmd(
    bench_path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
    name: str = typer.Argument(..., help="site name, e.g. site1.local"),
    install_app: list[str] = typer.Option(
        None, "--install-app", help="app to install (repeat for multiple)"
    ),
    admin_password: str | None = typer.Option(
        None,
        "--admin-password",
        help="Administrator password (prompted if omitted)",
    ),
    set_default: bool = typer.Option(False, "--set-default"),
    force: bool = typer.Option(False, "--force"),
    yes: bool = typer.Option(False, "--yes", "-y", help="no prompts"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Create a new site inside BENCH_PATH."""
    db_root = _require_mariadb_password(assume_yes=yes)
    admin = admin_password or (getpass("Administrator password: ") if not yes else None)
    if not admin:
        err_console.print("[red]--admin-password required when running with --yes[/]")
        raise typer.Exit(2)

    runner = CommandRunner(dry_run=dry_run)
    try:
        result = core_site.create_site(
            bench_path,
            name,
            db_root_password=db_root,
            admin_password=admin,
            install_apps=install_app or (),
            force=force,
            set_default=set_default,
            runner=runner,
        )
    except core_site.SiteAlreadyExistsError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(2) from err
    except core_site.SiteOperationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if result.info is not None:
        console.print(f"[green bold]✓ site {name} ready[/] (db: {result.info.db_name})")
    elif dry_run:
        console.print("[yellow]dry-run: nothing executed[/]")


@site_app.command("drop")
def drop_cmd(
    bench_path: Path = typer.Argument(..., exists=True, dir_okay=True, file_okay=False),
    name: str = typer.Argument(...),
    no_backup: bool = typer.Option(False, "--no-backup"),
    force: bool = typer.Option(False, "--force"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Drop a site (and its DB)."""
    db_root = _require_mariadb_password(assume_yes=yes)
    runner = CommandRunner(dry_run=dry_run)
    try:
        core_site.drop_site(
            bench_path,
            name,
            db_root_password=db_root,
            no_backup=no_backup,
            force=force,
            runner=runner,
        )
    except core_site.SiteNotFoundError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(2) from err
    except core_site.SiteOperationError as err:
        err_console.print(f"[red]{err}[/]")
        raise typer.Exit(1) from err

    if dry_run:
        console.print("[yellow]dry-run: nothing executed[/]")
    else:
        console.print(f"[green]site {name} dropped[/]")
