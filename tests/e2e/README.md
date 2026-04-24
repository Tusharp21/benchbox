# E2E smoke test

A clean-room install check: boots `ubuntu:22.04`, runs
`scripts/install.sh` from the working tree, then runs `verify.sh` inside
the container to assert:

- the venv, shims, `.desktop`, and icon landed in the right places
- every CLI subcommand's `--help` exits 0
- `benchbox install --dry-run --yes --skip-preflight` reaches the end
  without touching apt
- `benchbox bench list` works against an empty home

Kept narrow on purpose: a "does the real install actually do the
thing?" test would spend ~10 minutes provisioning MariaDB, Redis, etc.,
on every push. The dry-run shape-check catches 90% of regressions for
5% of the time.

## Run locally

```bash
docker build -f tests/e2e/Dockerfile -t benchbox-e2e .
docker run --rm benchbox-e2e
```

## CI

The `e2e` job in `.github/workflows/ci.yml` builds and runs this on
every push / PR to `main`.
