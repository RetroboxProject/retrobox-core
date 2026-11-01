#!/usr/bin/env bash
## PPSSPP INSTALLER
## Created: 1 November 2025
## Installs the official AppImage (x86_64 and aarch64), extracted
set -eo pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"

GITHUB_REPO="hrydgard/ppsspp"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/ppsspp"
TMP_DIR="$(mktemp -d)"

## FUNCTIONS

function error() {
    echo "[ERROR] $*."
    exit 1
}

function install_appimage(){
    # 1. Detect the architecture
    ARCH=$(uname -m)
    if [[ "$ARCH" == "x86_64" ]]; then
        SEARCH_ARCH="x86_64"
    elif [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        SEARCH_ARCH="aarch64"
    else
        error "Architecture not supported by this script: $ARCH"
    fi

    echo "[INFO] Detected architecture: $SEARCH_ARCH"
    echo "[INFO] Looking for the latest PPSSPP AppImage on GitHub..."

    # 2. Check curl
    #if ! command -v curl &> /dev/null; then
    #    echo "[INFO] Installing dependencies (curl)..."
    #    apt-get update && apt-get install -y curl || dnf install -y curl
    #fi

    # 3. Get the JSON of the latest release
    json=$(curl -sL "https://api.github.com/repos/$GITHUB_REPO/releases/latest")

    # 4. Extract the URL of the AppImage for this architecture
    APPIMAGE_URL=$(printf '%s\n' "$json" \
        | grep '"browser_download_url":' \
        | grep -i "\.AppImage" \
        | grep -i "$SEARCH_ARCH" \
        | head -n1 \
        | cut -d '"' -f4)

    if [[ -z "$APPIMAGE_URL" ]]; then
        rm -rf "$TMP_DIR"
        error "No AppImage for $SEARCH_ARCH found in the latest release of $GITHUB_REPO."
    fi

    echo "[INFO] Downloading: $APPIMAGE_URL"

    # 5. Prepare the directory and download
    mkdir -p "$INSTALL_DIR"
    curl -L "$APPIMAGE_URL" -o "$TMP_DIR/ppsspp.AppImage"

    # 6. Move and install
    mv "$TMP_DIR/ppsspp.AppImage" "$INSTALL_DIR/ppsspp.AppImage"
    chmod +x "$INSTALL_DIR/ppsspp.AppImage"
    mkdir -p "${INSTALL_DIR}/config"

    echo "[INFO] Extracting the AppImage..."
    (
        cd "${INSTALL_DIR}" || exit 1
        "${INSTALL_DIR}/ppsspp.AppImage" --appimage-extract >/dev/null 2>&1
        rm -f "${INSTALL_DIR}/squashfs-root"
        mv "${INSTALL_DIR}/AppDir" "${INSTALL_DIR}/app"
        rm "${INSTALL_DIR}/ppsspp.AppImage"
    )

    # 8. Clean up
    rm -rf "$TMP_DIR"
    echo "[INFO] AppImage installation completed."
}

function uninstall_app() {
    echo "[INFO] Looking for PPSSPP installations..."


    # Check for the AppImage
    if [[ -d "$INSTALL_DIR/app" ]]; then
        echo "[INFO] Uninstalling the AppImage version..."
        rm -rf "${INSTALL_DIR}/app"
    fi
}

## ENTRY POINT

echo "[INFO] Running the action for option: $1"

case "$1" in
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Unknown option."
        exit 1
        ;;
esac

exit 0
