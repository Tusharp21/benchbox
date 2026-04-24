# Contributing to benchbox

Thanks for your interest! benchbox is a Frappe bench installer and manager for
Ubuntu developers. We welcome issues, bug reports, and pull requests.

## Repo layout

```
core/     # Python library — all install + management logic
cli/      # Typer-based CLI frontend over core/
gui/      # Tauri desktop app (Rust + web) over core/
scripts/  # install.sh one-liner bootstrap
tests/    # end-to-end tests (Docker-based)
docs/     # user and contributor docs
```

All real logic lives in `core/`. The CLI and GUI are thin frontends. If you
find yourself adding logic to `cli/` or `gui/`, it probably belongs in
`core/`.

## Dev setup

```bash
# Clone + install the two Python packages in editable mode
git clone https://github.com/<owner>/benchbox
cd benchbox
uv pip install -e ./core[dev]
uv pip install -e ./cli[dev]

# Run checks
ruff check core/ cli/
mypy core/src cli/src
pytest core/tests cli/tests
```

## Filing issues

Use the issue templates under `.github/ISSUE_TEMPLATE/`. For bugs, please
include the output of `benchbox doctor` and the relevant log file from
`~/.benchbox/logs/`.

## Pull requests

- Branch off `main`
- One logical change per PR
- Include tests for new behavior
- Run `ruff format` before committing
- CI must be green before we merge
