#!/usr/bin/env bash
# RPCS3 (PlayStation 3): the AppImage of the newest build, extracted.
EMULATOR="rpcs3"
LABEL="RPCS3"
LEGACY=(rpcs3.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    local repository
    case "${ARCH}" in
        x86_64) repository="RPCS3/rpcs3-binaries-linux" ;;
        aarch64) repository="RPCS3/rpcs3-binaries-linux-arm64" ;;
        *) unavailable "RPCS3 has no AppImage for ${ARCH}." ;;
    esac
    local url
    # the asset names carry the version and commit, so they are looked up
    url="$(release_asset "github:${repository}" '\.AppImage$' any)"
    fetch "${url}" "${TMP_DIR}/rpcs3.AppImage"
    extract_appimage "${TMP_DIR}/rpcs3.AppImage"
}

installer_main "$@"
