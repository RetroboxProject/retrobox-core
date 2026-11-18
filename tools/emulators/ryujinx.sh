#!/usr/bin/env bash
# Ryujinx (Nintendo Switch, the Ryubing project): the AppImage of the latest
# release, extracted.
EMULATOR="ryujinx"
LABEL="Ryujinx"
LEGACY=(ryujinx.AppImage)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    local pattern
    case "${ARCH}" in
        x86_64) pattern='^(?!.*(arm|aarch)).*\.AppImage$' ;;
        aarch64) pattern='(arm64|aarch64).*\.AppImage$' ;;
        *) unavailable "Ryujinx has no AppImage for ${ARCH}." ;;
    esac
    local url
    url="$(release_asset forgejo:git.ryujinx.app/projects/Ryubing "${pattern}")"
    fetch "${url}" "${TMP_DIR}/ryujinx.AppImage"
    extract_appimage "${TMP_DIR}/ryujinx.AppImage"
}

installer_main "$@"
