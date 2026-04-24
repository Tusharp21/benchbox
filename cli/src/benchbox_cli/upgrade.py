"""`benchbox upgrade` — pull the latest benchbox from the install.sh URL.

Re-runs the same ``curl -fsSL … | bash`` pipeline a user would type to
install fresh. We execute it with ``bash -c`` so the child process replaces
the venv benchbox is currently running out of — the running process
finishes before install.sh starts tearing down the old venv, so we don't
yank the floor from under ourselves.
"""

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
    """Download and run the benchbox install.sh in-place.

    Equivalent to the install one-liner:

        curl -fsSL <install_url> | bash

    Your credentials (~/.benchbox/credentials.json) and session logs are
    left alone; only the venv + shims + .desktop are re-created.
    """
    console.print(f"[dim]fetching {install_url}[/]")
    console.print("[dim]this replaces the current benchbox install in-place…[/]\n")

    # We exec the curl-pipe-bash pipeline so our process is swapped out
    # atomically — the new install script gets a clean slate.
    cmd = f"curl -fsSL {install_url!r} | bash"
    try:
        exit_code = os.system(f"bash -c {cmd!r}")  # noqa: S605 — intentional shell pipeline
    except OSError as err:
        err_console.print(f"[red]failed to spawn bash: {err}[/]")
        raise typer.Exit(1) from err

    # os.system returns the waitpid-style status; extract the real exit code.
    rc = os.waitstatus_to_exitcode(exit_code) if exit_code != 0 else 0
    if rc != 0:
        err_console.print(f"[red]install.sh exited with status {rc}[/]")
        raise typer.Exit(rc)

    console.print("[green]✓ benchbox upgraded. Open a new terminal to pick up the new shims.[/]")
