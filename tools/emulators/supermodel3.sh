#!/usr/bin/env bash
# Supermodel (Sega Model 3): the Linux build of the newest release. It runs
# from its folder (Config/, NVRAM/, Saves/), so it is installed at the top of
# it; the Supermodel.ini there is the user's and is never overwritten.
EMULATOR="supermodel"
LABEL="Supermodel"
PORTABLE=1
KEEP=(Config/Supermodel.ini)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_archive() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "Supermodel only publishes x86_64 Linux builds."
    local url
    url="$(release_asset github:trzy/Supermodel 'linux.*\.tar\.gz$' any)"
    fetch "${url}" "${TMP_DIR}/supermodel.tar.gz"
    extract_archive "${TMP_DIR}/supermodel.tar.gz" "${STAGE}"
    require_executable supermodel
}

installer_main "$@"
