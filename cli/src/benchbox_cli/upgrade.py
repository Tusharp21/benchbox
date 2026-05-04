"""`benchbox upgrade` — re-run install.sh."""

from __future__ import annotations

import os

import typer

from benchbox_cli._output import console, err_console

upgrade_app = typer.Typer(help="pull the latest benchbox and reinstall")

DEFAULT_INSTALL_URL: str = (
    "https://raw.githubusercontent.com/Tusharp21/benchbox/main/scripts/install.sh"
)


@upgrade_app.callback(invoke_without_command=True)
def main(
    install_url: str = typer.Option(
        DEFAULT_INSTALL_URL,
        "--url",
        help="override the install.sh URL (for forks / non-main branches)",
    ),
) -> None:
    """Re-run install.sh in place. Credentials + logs are preserved."""
    console.print(f"[dim]fetching {install_url}[/]")
    console.print("[dim]this replaces the current benchbox install in-place…[/]\n")

    cmd = f"curl -fsSL {install_url!r} | bash"
    try:
        exit_code = os.system(f"bash -c {cmd!r}")  # noqa: S605
    except OSError as err:
        err_console.print(f"[red]failed to spawn bash: {err}[/]")
        raise typer.Exit(1) from err

    rc = os.waitstatus_to_exitcode(exit_code) if exit_code != 0 else 0
    if rc != 0:
        err_console.print(f"[red]install.sh exited with status {rc}[/]")
        raise typer.Exit(rc)

    console.print("[green]✓ benchbox upgraded. Open a new terminal to pick up the new shims.[/]")
