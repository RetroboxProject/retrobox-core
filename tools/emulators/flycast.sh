#!/usr/bin/env bash
# Flycast (Dreamcast, Naomi, Atomiswave), standalone: the official AppImage
# (x86_64), or a build from source for any architecture.
#
#   FLYCAST_CFLAGS   optimization flags of a source build (default:
#                    -O3 -march=native -pipe, for the machine it is built on)
EMULATOR="flycast"
LABEL="Flycast"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "Flycast only publishes an x86_64 AppImage."
    local url
    url="$(release_asset github:flyinghead/flycast 'x86_64.*\.AppImage$')"
    fetch "${url}" "${TMP_DIR}/flycast.AppImage"
    extract_appimage "${TMP_DIR}/flycast.AppImage"
}

function install_source() {
    install_packages \
        "build-essential cmake ninja-build git pkg-config libsdl2-dev libvulkan-dev
         libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev libpng-dev
         libzip-dev libcurl4-openssl-dev libasound2-dev libpipewire-0.3-dev libevdev-dev" \
        "gcc-c++ cmake ninja-build git pkgconf-pkg-config SDL2-devel vulkan-loader-devel
         vulkan-headers mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel
         libpng-devel libzip-devel libcurl-devel alsa-lib-devel pipewire-devel libevdev-devel"
    local flags="${FLYCAST_CFLAGS:--O3 -march=native -pipe}"
    git_clone https://github.com/flyinghead/flycast.git
    CFLAGS="${flags}" CXXFLAGS="${flags}" cmake_build
    mkdir -p "${STAGE}/bin"
    cp "${SRC_DIR}/build/flycast" "${STAGE}/bin/flycast" \
        || die "The build did not produce build/flycast"
    remove_sources
}

installer_main "$@"
