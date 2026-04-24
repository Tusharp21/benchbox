# benchbox-gui

Desktop UI for benchbox — Frappe bench manager on Ubuntu. PySide6 (Qt)
over the `benchbox_core` library, same process, no IPC.

## Layout

- **Left sidebar** — navigate between Benches / Install / Sites / Apps / Logs / Settings.
- **Top banner** — live CPU / RAM / disk + MariaDB + Redis state, polled every 2 s.
- **Main area** — list of benches on the machine; click one for details.

## Dev

```bash
pip install -e .[dev]
benchbox-gui
```
