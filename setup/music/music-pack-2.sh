#!/usr/bin/env bash
## MUSIC PACK VOL 2 INSTALLER
## CREATION DATE: September 6, 2026
set -eo pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/setup/lib/paths.sh"
INSTALL_DIR="${RETROBOX_MUSIC_DIR}"
TMP_DIR="$(mktemp -d)"
TARBALL_URL="https://store.batocera.org/music-pack-vol-2-1.0.0-1-any.pkg.tar.zst"
PACK_NAME="music-pack-2"
MANIFEST_DIR="${RETROBOX_STATEDIR}/packages/music"
MANIFEST_FILE="${MANIFEST_DIR}/${PACK_NAME}"

## FUNCTIONS
function error() {
    echo "[ERROR] $*." >&2
    exit 1
}

function install() {
    if ! command -v curl &> /dev/null; then
        echo "[INFO] curl not found. Attempting to install..."
        sudo dnf install -y curl || sudo apt-get install -y curl || error "Failed to install curl"
    fi
    if ! command -v zstd &> /dev/null; then
        echo "[INFO] zstd not found. Attempting to install..."
        sudo dnf install -y zstd || sudo apt-get install -y zstd || error "Failed to install zstd"
    fi

    mkdir -p "${INSTALL_DIR}"
    mkdir -p "${MANIFEST_DIR}"

    # Single download, single decompression. Everything else reads from local files.
    echo "[INFO] Downloading ${PACK_NAME}..."
    curl -sL "${TARBALL_URL}" -o "${TMP_DIR}/pack.tar.zst"

    echo "[INFO] Decompressing archive..."
    zstd -dc "${TMP_DIR}/pack.tar.zst" -o "${TMP_DIR}/pack.tar"

    echo "[INFO] Extracting ${PACK_NAME} to ${INSTALL_DIR}..."
    tar -xf "${TMP_DIR}/pack.tar" --strip-components=2 -C "${INSTALL_DIR}" "userdata/music/"

    echo "[INFO] Generating manifest at ${MANIFEST_FILE}..."
    tar -tf "${TMP_DIR}/pack.tar" \
        | grep "^userdata/music/" \
        | grep -v "/$" \
        | sed "s|^userdata/music/|music/|" \
        > "${MANIFEST_FILE}"

    rm -rf "${TMP_DIR}"
    echo "[INFO] Installation of ${PACK_NAME} completed."
}

function uninstall() {
    echo "[INFO] Uninstalling ${PACK_NAME}..."
    if [[ ! -f "${MANIFEST_FILE}" ]]; then
        echo "[WARN] Manifest not found at ${MANIFEST_FILE}. Cannot safely uninstall."
        return 1
    fi

    while IFS= read -r file; do
        if [[ -f "${RETROBOX_DATADIR}/${file}" ]]; then
            rm -f "${RETROBOX_DATADIR}/${file}"
            echo "[INFO] Removed ${file}"
        fi
    done < "${MANIFEST_FILE}"

    rm -f "${MANIFEST_FILE}"
    echo "[INFO] Uninstallation of ${PACK_NAME} completed."
}

## CALLS
case "$1" in
    "-i") install;;
    "-u"|"-d") uninstall;;
    *) exit 1;;
esac
exit 0