# Changelog

All notable changes to benchbox. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) +
[SemVer](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-24

First public release. Ubuntu 22.04 / 24.04 only; macOS is planned for a
later release. The project is three Python packages plus a bootstrap
installer:

- **benchbox-core** — library that owns all install + management logic.
- **benchbox-cli** — Typer frontend (`benchbox …`).
- **benchbox-gui** — PySide6 desktop frontend (`benchbox-gui`).

Both frontends call the same core library, so they never drift apart.

### Highlights

**End-to-end install story.** One command:

```bash
curl -fsSL https://raw.githubusercontent.com/Tusharp21/benchbox/main/scripts/install.sh | bash
```

That drops a per-user venv, `benchbox` + `benchbox-gui` + `benchbox-uninstall`
on `PATH`, a `.desktop` entry so the app shows up in the launcher, and an
icon. Uninstall is `benchbox-uninstall`.

**What's in 0.1.0**

- System installer (`benchbox install`) — detects Ubuntu 22.04 / 24.04,
  runs preflight, prompts once for a MariaDB root password (saved at
  `~/.benchbox/credentials.json` with 0600), then idempotently provisions
  six components: apt deps, MariaDB with Frappe-compatible charset, Redis,
  Node via nvm, patched-qt wkhtmltopdf, and the `frappe-bench` pip package
  via pipx.
- Bench lifecycle (CLI + GUI) — create, list, inspect, start/stop,
  migrate, backup, restore, self-upgrade.
- Site lifecycle (CLI + GUI) — create with install-apps, drop.
- App lifecycle (CLI + GUI) — get, install on site, uninstall.
- Discovery + introspection — scans `$HOME` for benches, reads Frappe
  version, Python, git branch, apps, and sites.
- Live stats banner (GUI) — CPU / RAM / disk / MariaDB + Redis state,
  polled every 2 s.
- Live session log viewer (GUI) — 1-second tail of
  `~/.benchbox/logs/<session>/session.log`.
- `benchbox upgrade` — re-runs `install.sh` in place.
- CI — 9-cell matrix (core × cli × gui × Py 3.10 / 3.11 / 3.12) plus a
  Docker-based E2E smoke test that provisions a fresh Ubuntu 22.04
  container and verifies the full install pipeline.
- 264 tests across the three packages; every touched file ruff + mypy
  `--strict` clean.

### Known limitations

- Ubuntu only. macOS + other distros are Phase 7.
- No `.deb` / `.AppImage` packaging yet — those land alongside future
  0.1.x releases.
- Visual polish (spacing, typography, colour balance) may still need
  iteration — the CLI is battle-tested; the GUI is functional but benefits
  from real-world feedback.

See the README's roadmap for what lands next.

[0.1.0]: https://github.com/Tusharp21/benchbox/releases/tag/v0.1.0
