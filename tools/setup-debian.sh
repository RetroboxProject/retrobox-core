#!/usr/bin/env bash
# Install Retrobox's system dependencies on Debian, Ubuntu, and Linux Mint.
# Tested on Debian 13 and Linux Mint 22.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
RETROBOX_ROOTDIR="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"

# shellcheck source=lib/log.sh
source "${SCRIPT_DIR}/lib/log.sh"

# shellcheck source=lib/deps.sh
source "${SCRIPT_DIR}/lib/deps.sh"

log_info "Installing system dependencies (apt)..."
mapfile -t _pkgs < <(deps_apt_args "${SCRIPT_DIR}/deps/debian.list")
mapfile -t _rec < <(deps_apt_args "${SCRIPT_DIR}/deps/recommended-debian.list")
sudo apt-get update
sudo apt-get install -y "${_pkgs[@]}"
sudo apt-get install -y "${_rec[@]}" || log_warn "Some recommended packages could not be installed."

log_info "Installing udev rules..."
sudo cp "${RETROBOX_ROOTDIR}/system/udev/"*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger || true

log_ok "System dependencies successfully installed."
