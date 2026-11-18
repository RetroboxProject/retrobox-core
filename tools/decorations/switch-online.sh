#!/usr/bin/env bash
# The "Switch Online" bezel pack, into <bezels>/switch-online.
#   -i  install (or update)      -u  uninstall
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/../.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=tools/lib/paths.sh
source "${ROOT_DIR}/tools/lib/paths.sh"
# shellcheck source=tools/lib/log.sh
source "${ROOT_DIR}/tools/lib/log.sh"

readonly PACK="switch-online"
readonly URL="https://github.com/manu-creative-411/batocera-overlay-switchonline/archive/refs/heads/main.tar.gz"
readonly INSTALL_DIR="${RETROBOX_BEZELS_DIR}/${PACK}"

function install_pack() {
    local work
    work="$(mktemp -d)"
    # shellcheck disable=SC2064  # expand now: the folder of this call
    trap "rm -rf '${work}'" EXIT
    log_info "Downloading the ${PACK} bezels..."
    curl -fL --retry 3 --progress-bar -o "${work}/pack.tar.gz" "${URL}" \
        || { log_err "The download of ${URL} failed"; exit 1; }
    mkdir -p "${work}/pack"
    tar -xzf "${work}/pack.tar.gz" -C "${work}/pack" --strip-components=1
    rm -rf "${INSTALL_DIR}.new"
    mv "${work}/pack" "${INSTALL_DIR}.new"
    rm -rf "${INSTALL_DIR}"
    mkdir -p "$(dirname "${INSTALL_DIR}")"
    mv "${INSTALL_DIR}.new" "${INSTALL_DIR}"
    # the file list of the former installer, no longer needed
    rm -f "${RETROBOX_STATEDIR}/packages/decorations/${PACK}"
    log_ok "The ${PACK} bezels are in ${INSTALL_DIR}."
}

function uninstall_pack() {
    rm -rf "${INSTALL_DIR}"
    rm -f "${RETROBOX_STATEDIR}/packages/decorations/${PACK}"
    log_ok "The ${PACK} bezels were removed."
}

case "${1:-}" in
    -i) install_pack ;;
    -u) uninstall_pack ;;
    *)
        echo "Usage: $(basename "$0") -i | -u" >&2
        exit 1
        ;;
esac
