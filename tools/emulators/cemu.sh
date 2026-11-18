#!/usr/bin/env bash
# Cemu (Wii U): the official AppImage, extracted.
EMULATOR="cemu"
LABEL="Cemu"
LEGACY=(cemu.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "Cemu only publishes an x86_64 AppImage."
    local url
    url="$(release_asset github:cemu-project/Cemu 'x86_64.*\.AppImage$')"
    fetch "${url}" "${TMP_DIR}/cemu.AppImage"
    extract_appimage "${TMP_DIR}/cemu.AppImage"
}

installer_main "$@"
