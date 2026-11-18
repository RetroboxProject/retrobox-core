#!/usr/bin/env bash
# Eden (Nintendo Switch): the AppImage of the latest release, extracted.
EMULATOR="eden-emu"
LABEL="Eden"
LEGACY=(eden-emu.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    local pattern
    case "${ARCH}" in
        x86_64) pattern='^(?!.*(arm|aarch)).*\.AppImage$' ;;
        aarch64) pattern='(arm64|aarch64).*\.AppImage$' ;;
        *) unavailable "Eden has no AppImage for ${ARCH}." ;;
    esac
    local url
    url="$(release_asset forgejo:git.eden-emu.dev/eden-emu/eden "${pattern}")"
    fetch "${url}" "${TMP_DIR}/eden.AppImage"
    extract_appimage "${TMP_DIR}/eden.AppImage"
}

installer_main "$@"
