#!/usr/bin/env bash
## CEMU INSTALLER
## Created: 19 May 2026
## Installs the official AppImage (x86_64)

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
GITHUB_REPO="cemu-project/Cemu"
APPIMAGE_DIR="${RETROBOX_EMULATORS_DIR}/cemu"

## FUNCTIONS

function error(){
    echo "[ERROR] $*."
    exit 1
}

function install_appimage(){
    echo "[INFO] Looking for the latest Cemu AppImage (x86_64) on GitHub..."

    # Get the download URL of the latest release from the GitHub API (filtering by AppImage and x86_64)
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep -i "x86_64" | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

    if [ -z "${DOWNLOAD_URL}" ]; then
        error "Could not get the AppImage download URL from GitHub"
    fi

    echo "[INFO] Downloading: ${DOWNLOAD_URL}"
    mkdir -p "${APPIMAGE_DIR}"
    curl -L "${DOWNLOAD_URL}" -o "${APPIMAGE_DIR}/cemu.AppImage"

    if [ $? -ne 0 ]; then
        error "Error while downloading the AppImage"
    fi

    echo "[INFO] Setting permissions..."
    chmod +x "${APPIMAGE_DIR}/cemu.AppImage"
    mkdir -p "${APPIMAGE_DIR}/config"

    echo "[INFO] AppImage installation completed."
}

function uninstall_app(){
    echo "[INFO] Looking for Cemu installations..."
    local found=0

    # Check for and uninstall the AppImage
    if [ -d "$APPIMAGE_DIR" ]; then
        echo "[INFO] Uninstalling the AppImage version..."
        rm -rf "$APPIMAGE_DIR"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No Cemu installation found."
    else
        echo "[INFO] Uninstallation completed."
    fi
}

## ENTRY POINT


if [ -z "$1" ]; then
    echo "Usage: $0 [-i | -u]"
    echo "  -i : Install the AppImage (x86_64, from GitHub)"
    echo "  -u : Uninstall"
    exit 1
fi

echo "[INFO] Running the action for option: $1"

case $1 in
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Unknown option."
        exit 1
        ;;
esac

exit 0
