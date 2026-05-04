# benchbox

> Frappe bench installer and manager for Ubuntu developers.

**Status:** v0.1.0 — first public release. **Primary OS:** Ubuntu 22.04 / 24.04. macOS support planned.

A desktop app + CLI that handles the painful parts of running Frappe locally:
MariaDB charset, wkhtmltopdf patched-qt, Node 18 via nvm, Redis, and `bench
init` quirks. One install, one dashboard, every common bench/site/app
operation a click away.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Tusharp21/benchbox/main/scripts/install.sh | bash
```

Drops a per-user venv at `~/.local/share/benchbox`, creates `benchbox` and
`benchbox-gui` shims in `~/.local/bin`, and registers a `.desktop` entry.

If `~/.local/bin` isn't on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## First run

End-to-end, fresh box:

```bash
benchbox quickstart
```

Or click the launcher icon (or `benchbox-gui`), open **Install** in the
sidebar, then **Benches** → **New bench**.

## What you get

- **Tabbed bench detail page** — `[Apps] [site1] [site2] ... [Free terminal]`.
  Switching to a site tab automatically scopes the dock's actions and the
  embedded runner to that site.
- **Per-app cards** — Install on site / Uninstall / Switch branch / Remove.
- **Per-site action grid** — Migrate / Clear cache / Backup / Pause-resume
  scheduler / Toggle maintenance mode. State pills show what's currently on
  or paused.
- **Sticky bottom dock** — `bench start` Start/Stop, status dot, live URL,
  collapsible log. Per-site Open in browser + Drop site (typed confirm)
  appear when a site tab is active.
- **Multi-bench in parallel** — every running `bench start` is tracked in
  one app-level process manager. Switching views never kills a bench.
- **Full subprocess cleanup on quit** — closing the window terminates every
  in-flight `bench start` and any runner commands (SIGTERM then SIGKILL).
- **Live system stats** — CPU / RAM / disk / Node / MariaDB / Redis pills
  at the top of every page.

## Screenshots

> Drop screenshots at `docs/screenshots/`.

| | |
| :---: | :---: |
| ![Bench list](docs/screenshots/benches.png) | ![Bench detail](docs/screenshots/bench-detail.png) |
| Bench list with live system stats | Tabbed bench detail with sticky dock |
| ![Site tab](docs/screenshots/site-tab.png) | ![Install](docs/screenshots/install.png) |
| Per-site working area: info table, maintenance grid, runner | Installer: preflight pills + component cards + live log |

## How to use it

[**docs/user-guide.md**](docs/user-guide.md) — install → first bench → GUI
tour → CLI reference → common workflows → troubleshooting.

## CLI

```
benchbox install        # prereqs (MariaDB, Redis, Node, wkhtmltopdf, bench CLI)
benchbox quickstart     # full provision + bench + site in one shot
benchbox bench list     # every bench under $HOME
benchbox bench info <path>
benchbox site new <bench-path> <site-name>
benchbox app get <bench-path> <git-url> --branch <name>
benchbox app install <bench-path> --site <name> <app>
benchbox stats          # one-shot CPU/RAM/services snapshot
benchbox upgrade        # re-run install.sh in place
```

`--help` works on every command.

## Upgrade and uninstall

```bash
benchbox upgrade        # re-runs install.sh; credentials and logs preserved
benchbox-uninstall      # removes venv + shims + .desktop; leaves ~/.benchbox/
```

To wipe credentials and logs too:

```bash
rm -rf ~/.benchbox
```

## Installing from a fork

```bash
BENCHBOX_REPO=https://github.com/you/benchbox.git \
BENCHBOX_REF=some-branch \
  curl -fsSL https://raw.githubusercontent.com/you/benchbox/some-branch/scripts/install.sh | bash
```

## Repo layout

```
core/      Python library — all install + management logic
cli/       Typer-based CLI frontend
gui/       PySide6 desktop app
scripts/   install.sh / uninstall.sh
assets/    app icon
tests/     Docker-based end-to-end tests
docs/      user-guide.md and screenshots
```

## Roadmap

- [x] **Phase 0** — Foundation (scaffold, CI, license, templates)
- [x] **Phase 1** — Core: discovery + introspection + live stats
- [x] **Phase 2** — Core: installer (deps, MariaDB, Node, Redis, wkhtmltopdf, bench CLI)
- [x] **Phase 3** — Core: bench / site / app operations
- [x] **Phase 4** — CLI frontend
- [x] **Phase 5** — Desktop GUI
- [x] **Phase 6** — Tabbed detail page, per-site context, sticky process dock, scheduler / maintenance toggles, branch switcher
- [x] **Phase 7 (MVP)** — `install.sh` bootstrap, `.desktop` integration, `benchbox upgrade`
- [ ] **Phase 8** — Per-site backup browser, site-config editor, logs-per-site viewer
- [ ] **Phase 9** — Production setup (nginx / supervisor / lets-encrypt)
- [ ] **Phase 10** — macOS support, signed `.deb`, AppImage

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE)
