#!/usr/bin/env bash
## RETROBAT BEZELS INSTALLER
## Installs the RetroBat bezel collection: the default bezels Retrobox falls
## back to after the user's own ones (RETROBOX_BEZELS_DIR). They are not part
## of the Retrobox package or repository: this clones them (shallow) into
## RETROBOX_BEZELS_DEFAULT_DIR, under the user's data directory, so running
## -i again simply updates them in place.
##
##   retrobat-bezels.sh -i     install or update
##   retrobat-bezels.sh -u     remove
set -eo pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_BEZELS_DEFAULT_DIR}"
REPO_URL="https://github.com/RetroBat-Official/retrobat-bezels.git"

## FUNCTIONS
function error() {
    echo "[ERROR] $*." >&2
    exit 1
}

function install() {
    command -v git &> /dev/null || error "git is required (sudo apt install git / sudo dnf install git)"

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        echo "[INFO] Updating RetroBat bezels in ${INSTALL_DIR}..."
        # The directory is managed by this script: local edits are discarded.
        git -C "${INSTALL_DIR}" fetch --depth 1 origin HEAD
        git -C "${INSTALL_DIR}" reset --hard FETCH_HEAD
    elif [[ -d "${INSTALL_DIR}" && -n "$(ls -A "${INSTALL_DIR}")" ]]; then
        error "${INSTALL_DIR} exists and was not installed by this script; move it away first"
    else
        echo "[INFO] Downloading RetroBat bezels into ${INSTALL_DIR}..."
        mkdir -p "$(dirname "${INSTALL_DIR}")"
        git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
    fi
    echo "[INFO] Installation of the RetroBat bezels completed."
}

function uninstall() {
    echo "[INFO] Uninstalling the RetroBat bezels..."
    if [[ ! -d "${INSTALL_DIR}/.git" ]] \
        || [[ "$(git -C "${INSTALL_DIR}" config --get remote.origin.url 2>/dev/null)" != "${REPO_URL}" ]]; then
        echo "[WARN] ${INSTALL_DIR} was not installed by this script. Not removing it."
        return 1
    fi
    rm -rf "${INSTALL_DIR}"
    echo "[INFO] Uninstallation of the RetroBat bezels completed."
}

## CALLS
case "$1" in
    "-i") install;;
    "-u"|"-d") uninstall;;
    *) exit 1;;
esac
exit 0
