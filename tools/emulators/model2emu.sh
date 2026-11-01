#!/usr/bin/env bash
## MODEL2EMU (SEGA MODEL 2) INSTALLER
## Created: 23 May 2026
## Changes: set up for a custom Wine environment

## VARIABLES
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"

DOWNLOAD_URL="https://github.com/batocera-linux/model2emu/raw/refs/heads/main/m2emulator.zip"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/model2emu"
EMU_DIR="$INSTALL_DIR/drive_c/model2emu"

## FUNCTIONS

function error(){
    echo "[ERROR] $*."
    exit 1
}

function check_dependencies(){
    if ! command -v wine >/dev/null 2>&1; then
        error "Wine is not installed on the system. Install it before continuing"
    fi
    if ! command -v unzip >/dev/null 2>&1; then
        error "The 'unzip' tool is not installed. Install it before continuing"
    fi
}

function m2emu_wine_install(){
    echo "[INFO] Checking the system dependencies..."
    check_dependencies

    echo "[INFO] Creating the directory and initializing the WINEPREFIX..."
    mkdir -p "$INSTALL_DIR"

    echo "[INFO] Creating the emulator directory..."
    mkdir -p "$EMU_DIR"

    echo "[INFO] Downloading m2emulator.zip from the Batocera repository..."
    TMP_ZIP=$(mktemp /tmp/m2emu_XXXXXX.zip)
    curl -L "$DOWNLOAD_URL" -o "$TMP_ZIP"

    if [ $? -ne 0 ]; then
        rm -f "$TMP_ZIP"
        error "Error while downloading the zip file"
    fi

    echo "[INFO] Extracting the files into the destination path..."
    unzip -o "$TMP_ZIP" -d "$EMU_DIR" >/dev/null
    rm -f "$TMP_ZIP"

    echo "[INFO] Model2Emu installed successfully."
}

function m2emu_uninstall(){
    echo "[INFO] Looking for Model2Emu installations..."
    local found=0

    # Check for and remove the Wine/files tree
    if [ -d "$INSTALL_DIR" ]; then
        echo "[INFO] Removing the WINEPREFIX and the emulator files in ${INSTALL_DIR}..."
        rm -rf "$INSTALL_DIR"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No Model2Emu installation found."
    else
        echo "[INFO] Uninstallation completed."
    fi
}

## ENTRY POINT

if [ -z "$1" ]; then
    echo "Usage: $0 [-i | -u]"
    echo "  -i : Install, setting up its own WINEPREFIX in ${INSTALL_DIR} and downloading the files"
    echo "  -u : Uninstall completely (removes the files and the WINEPREFIX)"
    exit 1
fi

echo "[INFO] Running the action for option: $1"

case $1 in
    "-i") m2emu_wine_install;;
    "-u") m2emu_uninstall;;
    *)
        echo "[ERROR] Unknown option."
        exit 1
        ;;
esac

exit 0
