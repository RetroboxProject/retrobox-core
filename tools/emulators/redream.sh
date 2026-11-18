#!/usr/bin/env bash
# Redream (Dreamcast): the latest development build from redream.io. It is
# portable (redream.cfg and its saves live next to the executable), so it
# is installed at the top of its folder.
EMULATOR="redream"
LABEL="Redream"
PORTABLE=1
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly DOWNLOAD_PAGE="https://redream.io/download"

function install_archive() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "Redream only publishes x86_64 Linux builds."
    local page path
    # no API: the newest tarball listed under "Development Releases"
    page="$(curl -fsSL --retry 3 "${DOWNLOAD_PAGE}")" || die "Could not read ${DOWNLOAD_PAGE}"
    path="$(sed -n '/Development Releases/,$p' <<<"${page}" \
        | grep -oE '/download/redream\.x86_64-linux-v[0-9][^"]*\.tar\.gz' | head -n 1 || true)"
    [[ -n "${path}" ]] || die "No Linux build found in ${DOWNLOAD_PAGE}"
    fetch "https://redream.io${path}" "${TMP_DIR}/redream.tar.gz"
    extract_archive "${TMP_DIR}/redream.tar.gz" "${STAGE}"
    require_executable redream
}

installer_main "$@"
