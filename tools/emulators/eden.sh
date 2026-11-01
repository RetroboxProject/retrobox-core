#!/usr/bin/env bash
## SWITCH EMULATOR INSTALLER - EDEN (FORGEJO API VERSION)
## Changed: 2026 (adapted to git.eden-emu.dev)
set -o pipefail

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/eden-emu"
TMP_DIR="$(mktemp -d)"
REPO_OWNER="eden-emu"
REPO_NAME="eden"
API_URL="https://git.eden-emu.dev/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

## FUNCTIONS
function error() {
    echo "[ERROR] $*"
    exit 1
}

function appimage_install(){
    # 3. Check the critical dependencies (curl and jq)
    if ! command -v curl &> /dev/null; then
        echo "Installing curl..."
        if command -v dnf &> /dev/null; then dnf install -y curl; else apt-get update && apt-get install -y curl; fi
    fi

    if ! command -v jq &> /dev/null; then
        echo "Installing jq..."
        if command -v dnf &> /dev/null; then dnf install -y jq; else apt-get update && apt-get install -y jq; fi
    fi

    # 4. Get the JSON from the Forgejo API
    echo "Connecting to the git.eden-emu.dev API..."
    json=$(curl -sL -H "Accept: application/json" "$API_URL")

    if [[ -z "$json" || "$json" == *"404 Not Found"* ]]; then
        error "Could not connect to the API, or the repository does not exist."
    fi

    # 5. Extract tag_name
    TAG_NAME=$(echo "$json" | jq -r '.tag_name')
    echo "Latest version found: $TAG_NAME"

    # 6. Extract the AppImage URL from the Forgejo assets
    # Keep .AppImage files that are not zsync and are for x86_64
    APPIMAGE_URL=$(echo "$json" | jq -r '.assets[] |
        select(.name | endswith(".AppImage")
        and (contains("arm") or contains("aarch") or contains("AppImage.zsync") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$APPIMAGE_URL" || "$APPIMAGE_URL" == "null" ]]; then
        error "No valid AppImage found in the latest Forgejo release."
    fi

    echo "Downloading from: $APPIMAGE_URL"

    # 7. Prepare the installation directory
    mkdir -p "${INSTALL_DIR}/config"

    # 8. Download and move
    curl -L "${APPIMAGE_URL}" -o "${TMP_DIR}/eden-emu.AppImage" || error "Error while downloading the file."

    mv "$TMP_DIR/eden-emu.AppImage" "${INSTALL_DIR}/eden-emu.AppImage"
    chmod +x "${INSTALL_DIR}/eden-emu.AppImage"

    # 9. Clean up the temporary directory
    rm -rf "${TMP_DIR}"

    echo "Eden Emulator ($TAG_NAME) installed successfully!"
}

function uninstall() {
    echo "Uninstalling Eden Emulator..."
    rm -rf "${INSTALL_DIR}"
    echo "Uninstallation completed."
}

case "$1" in
    -i) appimage_install ;;
    -u) uninstall ;;
    *) echo "Usage: $0 {-i (install) | -u (uninstall)}" ; exit 1 ;;
esac

exit 0
