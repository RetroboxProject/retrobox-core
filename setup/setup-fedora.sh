#!/usr/bin/env bash
# Install Retrobox's system dependencies on Fedora.
# Tested on Fedora 39+. Requires RPM Fusion (free) for some multimedia
# packages. To enable RPM Fusion if you don't have it:
#   sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
RETROBOX_ROOTDIR="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"

# shellcheck source=lib/log.sh
source "${SCRIPT_DIR}/lib/log.sh"

# shellcheck source=lib/deps.sh
source "${SCRIPT_DIR}/lib/deps.sh"

log_info "Installing system dependencies (dnf)..."
mapfile -t _pkgs < <(deps_list "${SCRIPT_DIR}/deps/fedora.list")
mapfile -t _rec < <(deps_list "${SCRIPT_DIR}/deps/recommended-fedora.list")
sudo dnf install -y "${_pkgs[@]}"
sudo dnf install -y "${_rec[@]}" || log_warn "Some recommended packages could not be installed."

log_info "Installing udev rules..."
# NOTE: this used to be "../resources/udev/*.rules", which only worked if you
# happened to run the script from inside setup/. Resolved against
# RETROBOX_ROOTDIR now so it works regardless of cwd (e.g. when called from
# retrobox.sh's setup orchestrator).
sudo cp "${RETROBOX_ROOTDIR}/resources/udev/"*.rules /etc/udev/rules.d/
sudo usermod -aG input "$(whoami)"
sudo udevadm control --reload-rules
sudo udevadm trigger

log_ok "System dependencies successfully installed."