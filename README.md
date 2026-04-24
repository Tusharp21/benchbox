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

> Not yet published. Once released:

```bash
# CLI (one-liner)
curl -sSL https://raw.githubusercontent.com/<owner>/benchbox/main/scripts/install.sh | bash

# GUI
# Download the latest .AppImage or .deb from GitHub Releases.
```

## Repo layout

```
core/     # Python library — all install + management logic
cli/      # Typer-based CLI frontend
gui/      # Tauri desktop app (Rust + web frontend)
scripts/  # install.sh bootstrap
tests/    # Docker-based end-to-end tests
docs/
```

## Roadmap

- [x] **Phase 0** — Foundation (scaffold, CI, license, templates)
- [ ] **Phase 1** — Core: discovery + introspection + live stats
- [ ] **Phase 2** — Core: installer (deps, MariaDB, Node, Redis, wkhtmltopdf)
- [ ] **Phase 3** — Core: bench/site/app operations
- [ ] **Phase 4** — CLI frontend
- [ ] **Phase 5** — Tauri GUI
- [ ] **Phase 6** — Release pipeline (signed `.deb` + `.AppImage`)
- [ ] **Phase 7** — E2E tests, macOS support

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
