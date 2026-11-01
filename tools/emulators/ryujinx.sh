#!/usr/bin/env bash
## SWITCH EMULATOR INSTALLER - RYUJINX / RYUBING
## Changed: May 2026
set -o pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"

REPO_OWNER="projects"
REPO_NAME="Ryubing"
API_URL="https://git.ryujinx.app/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/ryujinx"
TMP_DIR="$(mktemp -d)"

## CONTROL FUNCTIONS

function error(){
    echo "[ERROR] $*."
    rm -rf "$TMP_DIR" 2>/dev/null
    exit 1
}

function install_dependencies() {
    if ! command -v curl &> /dev/null || ! command -v jq &> /dev/null; then
        echo "[INFO] Installing the critical dependencies (curl and jq)..."
        if command -v dnf &> /dev/null; then
            dnf install -y curl jq
        elif command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y curl jq
        elif command -v pacman &> /dev/null; then
            pacman -Sy --noconfirm curl jq
        fi
    fi
}

function get_api_json() {
    install_dependencies
    echo "[INFO] Connecting to the git.ryujinx.app API..."
    JSON_DATA=$(curl -sL -H "Accept: application/json" "$API_URL")
    if [[ -z "$JSON_DATA" || "$JSON_DATA" == *"404 Not Found"* ]]; then
        error "No response from the Ryujinx API."
    fi
    TAG_NAME=$(echo "$JSON_DATA" | jq -r '.tag_name')
}

## INSTALLATION METHODS

function install_appimage(){
    get_api_json
    echo "[INFO] Picking the x64 AppImage for version: $TAG_NAME"

    DOWNLOAD_URL=$(echo "$JSON_DATA" | jq -r '.assets[] |
        select(.name | endswith(".AppImage") and (contains("arm") or contains("aarch") or contains("zsync") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$DOWNLOAD_URL" || "$DOWNLOAD_URL" == "null" ]]; then
        error "No valid x64 AppImage found in the assets."
    fi

    echo "[INFO] Downloading the AppImage..."
    curl -L "$DOWNLOAD_URL" -o "$TMP_DIR/ryujinx.AppImage" || error "Failed to download the AppImage."
    chmod +x "$TMP_DIR/ryujinx.AppImage"

    # Prepare a clean destination directory
    rm -rf "$INSTALL_DIR" && mkdir -p "${INSTALL_DIR}/config"

    # Move the files into place
    mv "${TMP_DIR}/ryujinx.AppImage" "${INSTALL_DIR}"
    rm -rf "$TMP_DIR"

    echo "[INFO] AppImage installation completed successfully."
}

function uninstall_all(){
    echo "[INFO] Looking for leftovers and active installations..."
    local found=0

    if [ -d "$INSTALL_DIR" ]; then
        echo "[INFO] Removing the installation in ${INSTALL_DIR}..."
        rm -rf "$INSTALL_DIR"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No previous installation found on the system."
    fi
}

## ENTRY POINT

if [ -z "$1" ]; then
    echo "Usage: $0 [-i | -u]"
    echo "  -i : Install the AppImage (Forgejo API)"
    echo "  -u : Uninstall"
    exit 1
fi

case $1 in
    "-i") install_appimage ;;
    "-u") uninstall_all ;;
    *)
        echo "[ERROR] Invalid option."
        exit 1
        ;;
esac

exit 0
