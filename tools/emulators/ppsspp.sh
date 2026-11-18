#!/usr/bin/env bash
# PPSSPP (PSP): the official AppImage (x86_64 and aarch64), extracted.
EMULATOR="ppsspp"
LABEL="PPSSPP"
LEGACY=(ppsspp.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    case "${ARCH}" in
        x86_64 | aarch64) ;;
        *) unavailable "PPSSPP has no AppImage for ${ARCH}." ;;
    esac
    local url
    url="$(release_asset github:hrydgard/ppsspp "${ARCH}.*\\.AppImage$")"
    fetch "${url}" "${TMP_DIR}/ppsspp.AppImage"
    extract_appimage "${TMP_DIR}/ppsspp.AppImage"
}

installer_main "$@"
