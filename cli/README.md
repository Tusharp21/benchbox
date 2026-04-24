# benchbox-cli

Typer-based command-line frontend for [benchbox-core](../core). All heavy
lifting lives in `core/` — this package is a thin command tree.

## Commands (planned)

| Command | Description |
|---|---|
| `benchbox install` | First-run system setup + create first bench + site |
| `benchbox doctor` | Check system readiness and report issues |
| `benchbox bench list` | List all benches discovered on this machine |
| `benchbox bench create` | Create a new bench (`bench init` wrapper) |
| `benchbox bench start <name>` | Start a bench in dev mode |
| `benchbox site create` | Create a new site on a bench |
| `benchbox app install` | Install an app onto a site |
| `benchbox uninstall` | Remove benchbox-managed state |
