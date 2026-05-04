# benchbox user guide

A walkthrough for setting up and managing Frappe benches with benchbox.

- [Install](#install)
- [Quick start](#quick-start)
- [GUI tour](#gui-tour)
  - [Top banner](#top-banner)
  - [Sidebar](#sidebar)
  - [Install page](#install-page)
  - [Bench list](#bench-list)
  - [Bench detail](#bench-detail)
- [CLI reference](#cli-reference)
- [Common workflows](#common-workflows)
- [Troubleshooting](#troubleshooting)

---

## Install

Ubuntu 22.04 or 24.04. One command:

```bash
curl -fsSL https://raw.githubusercontent.com/Tusharp21/benchbox/main/scripts/install.sh | bash
```

This drops a per-user venv at `~/.local/share/benchbox`, installs the
`benchbox` and `benchbox-gui` shims into `~/.local/bin`, and registers a
`.desktop` entry so benchbox appears in your app launcher.

If `~/.local/bin` isn't on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

To upgrade later:

```bash
benchbox upgrade
```

To uninstall:

```bash
benchbox-uninstall
```

Your saved credentials and logs at `~/.benchbox/` are kept. Delete that
directory by hand if you want them gone too.

---

## Quick start

Two paths.

### A. Provision and create a site in one shot

```bash
benchbox quickstart
```

Asks for the bench path, Frappe branch, site name, and the MariaDB +
admin passwords up front. Confirms once. Runs end-to-end with no
further prompts. Prints a success summary at the end (or shows where it
stopped on failure).

### B. Run the GUI

```bash
benchbox-gui
```

Or click the launcher icon. The first time, click **Install** in the
sidebar to install system prerequisites (apt packages, MariaDB, Redis,
Node 18 via nvm, wkhtmltopdf, the bench CLI). Then click **Benches** →
**New bench** to scaffold one.

---

## GUI tour

### Top banner

A horizontal strip across the top of the window with six pills:

- **cpu** — usage percent, polled every 2s
- **ram** — used / total GB
- **disk** — used / total GB at `~`
- **node** — Node version benchbox can find (prefers nvm Node 18, falls
  back to the system Node). Shows `missing` in red if no Node.
- **mariadb** — `active` / `inactive` from `systemctl is-active`
- **redis** — same, for `redis-server`

Right edge has a moon/sun icon to switch dark/light theme. The choice
persists.

### Sidebar

- **Benches** — the bench list (and the bench detail page when one is
  open).
- **Install** — system prerequisites and component status.
- **Sites** — read-only list of every site across every bench. Mutations
  live on the bench detail page.
- **Apps** — read-only list of every (bench, app) pair. Mutations live on
  the bench detail page.
- **Logs** — live tail of the current benchbox session log, with a picker
  for older sessions.
- **Documentation** — searchable command reference.
- **Settings** — credentials store, paths, version info.

### Install page

Three sections:

1. **Preflight** — pass/fail pills for sudo, network, disk, RAM, port
   3306/6379/8000. Hover for the failure message.
2. **Components** — a card per installer piece: apt packages, MariaDB,
   Redis, Node, wkhtmltopdf, bench CLI. Each card shows whether the
   component is already installed (probed via `dpkg-query` and
   `systemctl is-active`).
3. **Install log** — timestamped event log of the run.

A **Dry run** checkbox previews the steps without executing them. Click
**Run install** to actually run.

### Bench list

A card for every bench under your home directory. Each card shows path,
Frappe version, branch, app count, site count, and a green dot if
`bench start` is currently running for that bench.

- **Search by name or path** — substring match
- **Running only** — filters to in-flight benches
- **New bench** — opens the New Bench dialog (form → live `bench init`
  log → close)

Click anywhere on a card (or the **Open** button) to open the detail
view.

### Bench detail

The main work surface. Three areas:

#### Sticky header

Bench name (last path segment) as the heading, full path on the line
below in monospace, then version pills (`frappe`, `python`, `branch`).

Top-right action buttons:

- **Add...** dropdown
  - **New site** — `bench new-site`, with optional install-app picker
  - **Get app** — `bench get-app`, with optional GitHub PAT
  - **New app** — `bench new-app`
  - **Restore site** — `bench restore`
- **Bench...** dropdown
  - **Update bench** — pre-fills `bench update` in the Free terminal
  - **Migrate all sites** — pre-fills `bench migrate`
  - **Restart processes** — pre-fills `bench restart`
- **Open folder** — opens the bench directory in your file manager
- **Back to benches** — top-left, returns to the list

#### Tab strip

`[Apps]  [site1]  [site2]  ...  [Free terminal]`

A site tab per site under `sites/`. New site → new tab. Drop site → tab
disappears.

##### Apps tab

A card grid (2 or 3 columns based on width). Each card has the app
name, version pill, branch pill, and four buttons:

- **Install on site** — opens the install dialog with this app
  pre-selected
- **Uninstall from site** — site picker → typed confirm →
  `bench --site X uninstall-app <app>`
- **Switch branch** — input dialog → pre-fills `bench switch-to-branch
  <target> <app> --upgrade` in the Free terminal
- **Remove from bench** — typed confirm → `bench remove-app`

`frappe` has uninstall + remove disabled (it's the bench itself).

##### Site tab (one per site)

Three sections, top to bottom:

1. **Site info** — 2-column key/value table:
   - `db` — database name
   - `apps` — apps installed on this site (with a fallback to bench-wide
     apps when `apps.txt` is empty, since modern Frappe stores the
     truth in the DB)
   - `scheduler` — `running` (green) or `paused` (red)
   - `maintenance` — `off` (green) or `on` (red)

2. **Maintenance** — a 3-column button matrix:
   - **Migrate** (primary) — `bench --site X migrate`
   - **Clear cache** — `bench --site X clear-cache`
   - **Clear website cache** — `bench --site X clear-website-cache`
   - **Backup** — `bench --site X backup`
   - **Pause / Resume scheduler** — toggles `enable-scheduler` /
     `disable-scheduler`. Button label and colour reflect current state.
   - **Enter / Exit maintenance mode** — toggles
     `set-maintenance-mode on/off`.

   Every button pre-fills the embedded runner with the right
   `bench --site X …` command. You review and press Enter.

3. **Run any command** — a `bench` terminal locked to this site. Type
   anything; press Enter. Output streams into the log below. The site
   dropdown is hidden because the tab itself is the working context.

##### Free terminal

A bench-wide runner with no site lock. Use for `bench update`,
`bench migrate`, `bench restart`, or anything else that operates on the
bench rather than a site. Quick chips: Update bench, Migrate, Restart,
Clear cache, Clear website cache, Help.

Selecting a site from the dropdown changes the chips' default — e.g.
Migrate becomes `bench --site X migrate`.

#### Sticky bottom dock

Always visible. Shows:

- **Status dot** — gray (stopped), yellow (starting / stopping), green
  (running)
- **Status text** — the current state
- **URL link** — `http://localhost:<webserver_port>`, only when running
- **Start bench / Stop** — wraps `bench start` (Procfile-managed
  honcho). Multiple benches can run at once.
- **Open in browser** — only visible when both a site tab is active
  *and* the bench is running. Opens `http://<site>:<port>`.
- **Drop site** — only visible when a site tab is active. Opens the
  typed-name confirmation dialog, then runs `bench drop-site` through
  the site tab's runner so output streams into the same log. The
  password is masked in the displayed command.
- **Show / Hide logs** — collapses the bench-start log panel. Auto
  expands when the bench starts.

When you close the benchbox window, every running `bench start` and
in-flight `bench` command is terminated cleanly (SIGTERM, then SIGKILL
after 3s).

---

## CLI reference

```
benchbox <command> [options]
```

### Top-level

| Command | What it does |
|---|---|
| `benchbox install` | Run preflight + every installer component. Prompts for the MariaDB root password once. |
| `benchbox quickstart` | One-shot: install prereqs, create a bench, create a site. |
| `benchbox stats` | One-shot system snapshot (CPU, RAM, disk, services). |
| `benchbox upgrade` | Re-run `install.sh`. Credentials and logs preserved. |
| `benchbox-gui` | Launch the desktop app. |
| `benchbox-uninstall` | Remove the venv, shims, and `.desktop` entry. Leaves `~/.benchbox/`. |

### `benchbox bench`

| Command | What it does |
|---|---|
| `bench new <path>` | `bench init`. Defaults to Frappe `version-15`. |
| `bench list` | List every bench under `$HOME`. |
| `bench info <path>` | Frappe version, Python, branch, apps, sites. |
| `bench migrate <path> --site <name>` | `bench --site <name> migrate`. |
| `bench backup <path> --site <name> [--with-files]` | `bench --site <name> backup`. |
| `bench restore <path> --site <name> --sql <file.sql.gz>` | `bench --site <name> restore`. |

### `benchbox site`

| Command | What it does |
|---|---|
| `site new <bench-path> <site-name>` | `bench new-site`. |
| `site drop <bench-path> <site-name>` | `bench drop-site`. |

### `benchbox app`

| Command | What it does |
|---|---|
| `app get <bench-path> <git-url> [--branch X]` | `bench get-app`. |
| `app install <bench-path> --site <name> <app>` | `bench --site X install-app`. |
| `app uninstall <bench-path> --site <name> <app>` | `bench --site X uninstall-app`. |

Run any command with `--help` for full options.

---

## Common workflows

### First-time setup on a fresh Ubuntu box

```bash
curl -fsSL https://raw.githubusercontent.com/Tusharp21/benchbox/main/scripts/install.sh | bash
exec $SHELL                 # pick up new PATH
benchbox quickstart         # answers a few prompts, then runs
benchbox-gui                # open the dashboard
```

### Create a new bench

GUI: **Benches** → **New bench** → fill the form (path, Frappe branch,
Python binary). Watch the live `bench init` log; click **Close** when
it's green.

CLI:

```bash
benchbox bench new ~/work/frappe-bench-15 --branch version-15
```

### Add ERPNext to an existing bench

GUI: open the bench → **Add...** → **Get app** → paste
`https://github.com/frappe/erpnext` → pick branch `version-15`. Watch
the clone + pip install stream live. After it closes, the **Apps** tab
has an `erpnext` card; click **Install on site** to install it on a
specific site.

CLI:

```bash
benchbox app get ~/work/frappe-bench-15 https://github.com/frappe/erpnext --branch version-15
benchbox app install ~/work/frappe-bench-15 --site dev.local erpnext
```

### Switch all apps to a different Frappe version

GUI: **Apps** tab → click **Switch branch** on `frappe` → enter target
branch (e.g. `version-14`). The Free terminal opens with
`bench switch-to-branch version-14 frappe --upgrade` pre-filled. Press
Enter. Repeat for each app.

The `--upgrade` flag re-runs the post-install steps, so dependencies
and migrations get applied.

### Pause the scheduler for maintenance

GUI: open the site tab → **Maintenance** → **Pause scheduler**. The
runner gets pre-filled with `bench --site X disable-scheduler`. Press
Enter. The site info row above flips from `running` (green) to
`paused` (red).

To resume, click the same button (now labelled **Resume scheduler**).

### Drop a site

GUI: open the site tab → bottom dock → **Drop site**. Type the site
name in the confirmation popup. The runner echoes
`bench drop-site <name> --root-password ******** --no-backup` and
runs it. Output streams in the log. On success the site tab
disappears.

### Restore from a backup

GUI: **Add...** → **Restore site** → pick the site, pick the SQL dump
file, optionally the public/private file tarballs. Watch the live log.

CLI: use the bench's own `bench --site X restore` for now.

### Update the bench and migrate

GUI: header **Bench...** → **Update bench** opens the Free terminal
with `bench update` pre-filled. Press Enter. Then **Bench...** →
**Migrate all sites** → press Enter.

### Run two benches in parallel

Open one bench, click **Start bench** in the dock. Go back to the
benches list. Open another bench, click **Start bench** again. Both
will keep running with their own logs and URLs. Each bench's
`webserver_port` should be different — set it in
`<bench>/sites/common_site_config.json` to avoid port collisions.

---

## Troubleshooting

### "engine node incompatible: expected >=18"

You're on Ubuntu 22.04 where the apt-shipped Node is 12, and nvm
hasn't been sourced. Run **Install** from the GUI sidebar, or
`benchbox install` on the CLI — the Node component installs nvm and
Node 18 for the user. After it finishes, open a new terminal so the
shell rc files re-source.

benchbox always prepends nvm's Node 18 to the subprocess `PATH` before
calling `bench`, so `bench init` and `bench update` find the right
Node even when your interactive shell hasn't sourced nvm yet.

### "Bench instance already exists"

`bench init` returns exit 0 even when it refused to populate an
existing directory. benchbox checks for that and turns it into a
visible error. Pick a path that doesn't exist yet, or delete the old
one first.

### "MariaDB root password missing" when creating a site

Run **Install** at least once (it sets the root password and saves it
at `~/.benchbox/credentials.json` mode 0600). Or set it manually:

```bash
benchbox install   # prompts for it on first run
```

### `bench drop-site` hangs in the runner

The runner doesn't pipe stdin, so an interactive password prompt
will hang. The Drop site flow on the dock injects
`--root-password '<saved>'` automatically. If you typed
`bench drop-site` manually in a runner, include `--root-password`
yourself.

### A long-running migrate is still going when I close benchbox

Window close terminates every in-flight runner command and every
`bench start` process (SIGTERM, then SIGKILL after 3 seconds). If
you're in the middle of a migrate you don't want to lose, wait for
it to finish before closing the window.

### Where are the logs?

Sidebar → **Logs**. Or on disk:

```
~/.benchbox/logs/<timestamp>/session.log
```

Pre-existing benchbox sessions stay in their own folders. The current
session is always pinned at the top of the picker.

### Where is the MariaDB root password stored?

```
~/.benchbox/credentials.json   # mode 0600, plain JSON
```

This is intentional — Frappe's own `site_config.json` stores DB
credentials in the same form. Override the path with
`BENCHBOX_CONFIG_DIR=/somewhere/else`.

### How do I reset my preferences?

```bash
rm ~/.benchbox/preferences.json
```

Theme falls back to dark on next launch.

---

## Reporting issues

GitHub: <https://github.com/Tusharp21/benchbox/issues>

Attach `~/.benchbox/logs/<latest>/session.log` if relevant — it
contains every subprocess command + exit code at DEBUG level.
