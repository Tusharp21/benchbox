#!/usr/bin/env bash
# benchbox uninstaller.
#
# Normally invoked as `benchbox-uninstall` (a shim the installer leaves at
# ~/.local/bin/). This standalone copy is for recovering from a half-finished
# install, or when you've fetched just this script via curl.
#
# Usage:
#   ~/.local/share/benchbox/uninstall.sh
# or (standalone):
#   curl -sSL https://raw.githubusercontent.com/<you>/benchbox/main/scripts/uninstall.sh | bash

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
echo
echo "note: logs + saved credentials at ~/.benchbox/ were NOT removed."
echo "      remove with:  rm -rf ~/.benchbox"
