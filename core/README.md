# benchbox-core

Shared Python library powering both the CLI and GUI. Contains all Frappe bench
discovery, installation, and management logic — no UI concerns live here.

## Modules (planned)

- `detect` — OS / distro / existing-install detection
- `preflight` — RAM, disk, ports, internet, sudo availability checks
- `discovery` — scan the filesystem for existing Frappe benches
- `introspect` — read metadata (versions, apps, sites) from a discovered bench
- `stats` — live system stats (CPU, RAM, disk, service status)
- `deps` — system dependency installers (apt for Ubuntu)
- `mariadb` — MariaDB install + `utf8mb4` config
- `bench` — wrappers around `bench init`, `new-site`, `get-app`, etc.
- `logging` — structured logs to `~/.benchbox/logs/`
- `rollback` — undo partial installs on failure
