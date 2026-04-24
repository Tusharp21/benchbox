# benchbox

> Frappe bench installer and manager for Ubuntu developers.

**Status:** early development — not yet released. **Primary OS for v0.1:** Ubuntu 22.04 / 24.04. macOS support planned for a later release.

benchbox gives you two ways to install and manage Frappe locally:

- **CLI** — `benchbox install` walks you through a first-run setup, then `benchbox bench`, `benchbox site`, and `benchbox app` commands manage everything after.
- **GUI** — a desktop app with a live dashboard: top banner shows system stats, sidebar for quick navigation, main area lists every bench on your machine. Click a bench to see its apps, sites, versions, and services.

Under the hood, both frontends call the same Python core library, so they never drift apart.

## Why

Standard Frappe install is painful: MariaDB charset gotchas, the wkhtmltopdf patched-qt requirement, Node/Python version juggling, Redis services, and `bench init` quirks. benchbox collapses all of that into one command (or one click) and then sticks around as a dashboard for the benches it set up.

## Install

Ubuntu 22.04 / 24.04, one command:

```bash
curl -sSL https://raw.githubusercontent.com/<owner>/benchbox/main/scripts/install.sh | bash
```

That drops a per-user venv at `~/.local/share/benchbox`, creates
`benchbox` and `benchbox-gui` on your `PATH`, and registers a
`.desktop` entry so **benchbox shows up in your app launcher** with an
icon. You can launch the GUI by clicking it or by running
`benchbox-gui` in a terminal.

If `~/.local/bin` isn't on your `PATH` yet, add this to `~/.bashrc`:

```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

### Uninstall

```bash
benchbox-uninstall
```

Leaves `~/.benchbox/` (logs + saved credentials) untouched —
`rm -rf ~/.benchbox` if you want that gone too.

### Installing from a fork / a specific branch

```bash
BENCHBOX_REPO=https://github.com/you/benchbox.git \
BENCHBOX_REF=some-branch \
  curl -sSL https://raw.githubusercontent.com/you/benchbox/some-branch/scripts/install.sh | bash
```

Signed `.deb` + `.AppImage` packages are planned for Phase 6.

## Repo layout

```
core/     # Python library — all install + management logic
cli/      # Typer-based CLI frontend
gui/      # PySide6 desktop app
scripts/  # install.sh / uninstall.sh bootstrap
assets/   # app icon
tests/    # Docker-based end-to-end tests
docs/
```

## Roadmap

- [x] **Phase 0** — Foundation (scaffold, CI, license, templates)
- [x] **Phase 1** — Core: discovery + introspection + live stats
- [x] **Phase 2** — Core: installer (deps, MariaDB, Node, Redis, wkhtmltopdf)
- [x] **Phase 3** — Core: bench/site/app operations
- [x] **Phase 4** — CLI frontend
- [x] **Phase 5** — Desktop GUI (PySide6 — sidebar, stats banner, bench list/detail, installer) *(core views functional; sites/apps views still stub to the CLI; needs visual polish pass)*
- [ ] **Phase 6** — Release pipeline *(install.sh bootstrap + `.desktop` integration landed; signed `.deb` + `.AppImage` still pending)*
- [ ] **Phase 7** — E2E tests, macOS support

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
