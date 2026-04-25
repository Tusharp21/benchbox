"""benchbox — entrypoint for the CLI.

Wires the ``install``, ``stats``, ``bench``, ``site``, and ``app`` subcommand
groups into one Typer app. Nothing interesting happens here; the per-command
logic lives in the sibling modules.
"""

from __future__ import annotations

import typer

from benchbox_cli import __version__
from benchbox_cli.app import app_cli as _app_cli
from benchbox_cli.bench import bench_app as _bench_app
from benchbox_cli.install import install_app as _install_app
from benchbox_cli.quickstart import quickstart_app as _quickstart_app
from benchbox_cli.site import site_app as _site_app
from benchbox_cli.stats import stats_app as _stats_app
from benchbox_cli.upgrade import upgrade_app as _upgrade_app

app = typer.Typer(
    help="benchbox — Frappe bench installer and manager for Ubuntu",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(_quickstart_app, name="quickstart")
app.add_typer(_install_app, name="install")
app.add_typer(_upgrade_app, name="upgrade")
app.add_typer(_stats_app, name="stats")
app.add_typer(_bench_app, name="bench")
app.add_typer(_site_app, name="site")
app.add_typer(_app_cli, name="app")


@app.command("version")
def _version() -> None:
    """Print the CLI version."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
