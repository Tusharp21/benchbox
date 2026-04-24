"""`benchbox stats` — one-shot CPU/RAM/disk + service snapshot."""

from __future__ import annotations

import typer
from benchbox_core import logs, stats

from benchbox_cli._output import console, print_stats

stats_app = typer.Typer(help="inspect the host — live system stats, log locations")


@stats_app.callback(invoke_without_command=True)
def _stats_default(
    ctx: typer.Context,
) -> None:
    """Default: show the current system snapshot."""
    if ctx.invoked_subcommand is not None:
        return
    print_stats(stats.snapshot())


@stats_app.command("logs")
def logs_cmd() -> None:
    """Print the path of the current benchbox session log directory."""
    session = logs.current_session_dir()
    if session is None:
        session = logs.init_session()
    console.print(str(session))
