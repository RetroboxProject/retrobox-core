#!/usr/bin/env bash
# PCSX2 (PlayStation 2): the AppImage of the newest release, nightlies included.
EMULATOR="pcsx2"
LABEL="PCSX2"
LEGACY=(pcsx2.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "PCSX2 only publishes an x86_64 AppImage."
    local url
    url="$(release_asset github:PCSX2/pcsx2 '\.AppImage$' any)"
    fetch "${url}" "${TMP_DIR}/pcsx2.AppImage"
    extract_appimage "${TMP_DIR}/pcsx2.AppImage"
}

installer_main "$@"
