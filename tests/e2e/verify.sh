#!/usr/bin/env bash
# Post-install verification — runs inside the E2E Docker container.
#
# Each check fails the container (non-zero exit) on any regression. The
# goal is not to test Frappe itself (apt-installing MariaDB + bench init
# takes ~10 minutes in CI); it's to catch shape regressions in the
# installer, the CLI entry point, and the core library's dry-run path.

set -euo pipefail

BIN="${HOME}/.local/bin"

check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ ${name}"
    else
        echo "  ✗ ${name} FAILED" >&2
        "$@" || true
        exit 1
    fi
}

echo "== benchbox E2E verification =="
echo

echo "-- layout --"
check "benchbox binary on PATH"            test -x "${BIN}/benchbox"
check "benchbox-gui binary on PATH"        test -x "${BIN}/benchbox-gui"
check "benchbox-uninstall shim present"    test -x "${BIN}/benchbox-uninstall"
check "venv installed"                     test -d "${HOME}/.local/share/benchbox/venv"
check ".desktop entry installed"           test -f "${HOME}/.local/share/applications/benchbox.desktop"
check "icon installed"                     test -f "${HOME}/.local/share/icons/hicolor/scalable/apps/benchbox.svg"

echo
echo "-- CLI --"
check "benchbox version"                   benchbox version
check "benchbox --help"                    benchbox --help
check "benchbox bench --help"              benchbox bench --help
check "benchbox site --help"               benchbox site --help
check "benchbox app --help"                benchbox app --help
check "benchbox stats --help"              benchbox stats --help
check "benchbox install --help"            benchbox install --help

echo
echo "-- installer (dry-run) --"
mkdir -p "${HOME}/.benchbox"
chmod 700 "${HOME}/.benchbox"
# Pre-seed a MariaDB root password so --yes doesn't bail.
cat > "${HOME}/.benchbox/credentials.json" <<'JSON'
{"mariadb_root_password": "e2e-dummy"}
JSON
chmod 600 "${HOME}/.benchbox/credentials.json"

check "install --dry-run --yes --skip-preflight" \
    benchbox install --dry-run --yes --skip-preflight

echo
echo "-- discovery --"
check "bench list (empty home)"            benchbox bench list

echo
echo "✓ E2E passed"
