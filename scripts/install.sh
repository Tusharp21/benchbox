#!/usr/bin/env bash
# benchbox — per-user bootstrap installer for Ubuntu.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/<you>/benchbox/main/scripts/install.sh | bash
#
# Env-var knobs (rarely needed):
#   BENCHBOX_REPO    git URL to clone (default: the upstream repo)
#   BENCHBOX_REF     branch/tag/commit to install at (default: main)
#   BENCHBOX_SOURCE  local path to install from instead of git (for dev/testing)
#
# What this installs (per-user, no sudo):
#   ~/.local/share/benchbox/venv           — Python venv with core + cli + gui
#   ~/.local/bin/benchbox                  — CLI shim
#   ~/.local/bin/benchbox-gui              — GUI shim
#   ~/.local/bin/benchbox-uninstall        — uninstall shim
#   ~/.local/share/applications/benchbox.desktop
#   ~/.local/share/icons/hicolor/scalable/apps/benchbox.svg

set -euo pipefail

BENCHBOX_REPO="${BENCHBOX_REPO:-https://github.com/Tusharp21/benchbox.git}"
BENCHBOX_REF="${BENCHBOX_REF:-main}"
BENCHBOX_SOURCE="${BENCHBOX_SOURCE:-}"

INSTALL_PREFIX="${HOME}/.local/share/benchbox"
VENV_DIR="${INSTALL_PREFIX}/venv"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

color_red() { printf '\033[31m%s\033[0m\n' "$1" >&2; }
color_grn() { printf '\033[32m%s\033[0m\n' "$1"; }
color_dim() { printf '\033[2m%s\033[0m\n' "$1"; }
bold()      { printf '\033[1m%s\033[0m\n' "$1"; }

die() { color_red "error: $1"; exit 1; }

bold "benchbox installer"
echo

# --- pre-flight --------------------------------------------------------------

if [[ "${EUID}" -eq 0 ]]; then
    die "do not run as root — benchbox installs to ~/.local/"
fi

# Pick the newest available Python >= 3.10.
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        if "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
            PYTHON="${candidate}"
            break
        fi
    fi
done

if [[ -z "${PYTHON}" ]]; then
    die "benchbox needs Python 3.10+. Install with:  sudo apt install python3 python3-venv"
fi

if ! "${PYTHON}" -c 'import venv' >/dev/null 2>&1; then
    die "python3-venv is not installed. Install with:  sudo apt install python3-venv"
fi

if [[ -z "${BENCHBOX_SOURCE}" ]] && ! command -v git >/dev/null 2>&1; then
    die "git is required when installing from a repo. Install with:  sudo apt install git"
fi

color_dim "using Python: $(${PYTHON} --version) at $(command -v ${PYTHON})"

# --- source: git clone or local path -----------------------------------------

SOURCE_DIR=""
CLEANUP_TMP=""

if [[ -n "${BENCHBOX_SOURCE}" ]]; then
    SOURCE_DIR="$(cd "${BENCHBOX_SOURCE}" && pwd)"
    color_dim "installing from local source: ${SOURCE_DIR}"
else
    CLEANUP_TMP="$(mktemp -d)"
    trap 'rm -rf "${CLEANUP_TMP}"' EXIT
    color_dim "cloning ${BENCHBOX_REPO} @ ${BENCHBOX_REF}"
    git clone --depth 1 --branch "${BENCHBOX_REF}" "${BENCHBOX_REPO}" "${CLEANUP_TMP}/repo" >/dev/null 2>&1
    SOURCE_DIR="${CLEANUP_TMP}/repo"
fi

for subdir in core cli gui; do
    if [[ ! -f "${SOURCE_DIR}/${subdir}/pyproject.toml" ]]; then
        die "source at ${SOURCE_DIR} is missing ${subdir}/pyproject.toml"
    fi
done

# --- venv --------------------------------------------------------------------

mkdir -p "${INSTALL_PREFIX}" "${BIN_DIR}" "${DESKTOP_DIR}" "${ICON_DIR}"

if [[ -d "${VENV_DIR}" ]]; then
    color_dim "removing existing venv at ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
fi

color_dim "creating venv at ${VENV_DIR}"
"${PYTHON}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --disable-pip-version-check --quiet --upgrade pip

color_dim "installing benchbox-core, benchbox-cli, benchbox-gui"
"${VENV_DIR}/bin/pip" install --disable-pip-version-check --quiet \
    "${SOURCE_DIR}/core" \
    "${SOURCE_DIR}/cli" \
    "${SOURCE_DIR}/gui"

# --- icon --------------------------------------------------------------------

if [[ -f "${SOURCE_DIR}/assets/benchbox.svg" ]]; then
    cp "${SOURCE_DIR}/assets/benchbox.svg" "${ICON_DIR}/benchbox.svg"
    color_dim "installed icon to ${ICON_DIR}/benchbox.svg"
else
    color_dim "warning: assets/benchbox.svg not found; skipping icon install"
fi

# --- shims -------------------------------------------------------------------

install_shim() {
    local name="$1"
    cat > "${BIN_DIR}/${name}" <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/${name}" "\$@"
EOF
    chmod +x "${BIN_DIR}/${name}"
}

install_shim benchbox
install_shim benchbox-gui

# Uninstall shim points at the script we install below.
cat > "${BIN_DIR}/benchbox-uninstall" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_PREFIX}/uninstall.sh" "\$@"
EOF
chmod +x "${BIN_DIR}/benchbox-uninstall"

# --- uninstall helper (copied into the install prefix for self-removal) ------

cat > "${INSTALL_PREFIX}/uninstall.sh" <<'UNINSTALL_EOF'
#!/usr/bin/env bash
set -euo pipefail
INSTALL_PREFIX="${HOME}/.local/share/benchbox"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

echo "removing ${INSTALL_PREFIX}"
rm -rf "${INSTALL_PREFIX}"
for f in benchbox benchbox-gui benchbox-uninstall; do
    rm -f "${BIN_DIR}/${f}"
done
rm -f "${DESKTOP_DIR}/benchbox.desktop"
rm -f "${ICON_DIR}/benchbox.svg"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi
echo "✓ benchbox uninstalled."
echo "note: logs + saved credentials at ~/.benchbox/ were NOT removed."
echo "      remove with: rm -rf ~/.benchbox"
UNINSTALL_EOF
chmod +x "${INSTALL_PREFIX}/uninstall.sh"

# --- .desktop ----------------------------------------------------------------

cat > "${DESKTOP_DIR}/benchbox.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=benchbox
GenericName=Frappe Bench Manager
Comment=Install and manage Frappe benches for local development
Exec=${BIN_DIR}/benchbox-gui
Icon=benchbox
Terminal=false
Categories=Development;IDE;
Keywords=frappe;erpnext;bench;python;
StartupNotify=true
StartupWMClass=benchbox
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi

# --- PATH hint ---------------------------------------------------------------

echo
color_grn "✓ benchbox installed"
echo
echo "  Next step (one shot — provisions Frappe + creates your first bench & site):"
echo
echo "      benchbox quickstart"
echo
echo "  Or pick what to run yourself:"
echo "    CLI:         benchbox --help"
echo "    GUI:         benchbox-gui      (also available from your app launcher)"
echo "    uninstall:   benchbox-uninstall"
echo
if ! printf ':%s:' "${PATH}" | grep -q ":${BIN_DIR}:"; then
    color_red "heads up: ${BIN_DIR} is not on your PATH."
    echo "         Add this line to ~/.bashrc or ~/.profile:"
    echo "           export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    echo "         then open a new terminal."
fi
