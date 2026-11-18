#!/usr/bin/env bash
# Dolphin (GameCube, Wii): the AppImage of pkgforge-dev (Dolphin publishes
# none of its own), or a build from source.
EMULATOR="dolphin-emu"
LABEL="Dolphin"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function install_appimage() {
    local url
    url="$(release_asset github:pkgforge-dev/Dolphin-emu-AppImage "${ARCH}.*\\.AppImage$")"
    fetch "${url}" "${TMP_DIR}/dolphin.AppImage"
    extract_appimage "${TMP_DIR}/dolphin.AppImage"
}

function install_source() {
    install_packages \
        "build-essential cmake ninja-build git pkg-config gettext librsvg2-bin
         libgl1-mesa-dev libegl1-mesa-dev libx11-dev libxrandr-dev libxi-dev
         libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev
         libudev-dev libevdev-dev libsdl3-dev libfmt-dev glslang-dev glslang-tools
         libpugixml-dev libenet-dev libxxhash-dev libbz2-dev liblzma-dev libzstd-dev
         zlib1g-dev liblzo2-dev liblz4-dev libspng-dev libcubeb-dev libusb-1.0-0-dev
         libminiupnpc-dev libcurl4-openssl-dev libhidapi-dev libgtest-dev
         libasound2-dev libpulse-dev llvm-dev libbluetooth-dev
         qt6-base-dev qt6-base-private-dev qt6-svg-dev" \
        "gcc-c++ cmake ninja-build git pkgconf-pkg-config gettext
         mesa-libGL-devel mesa-libEGL-devel libX11-devel libXrandr-devel libXi-devel
         ffmpeg-devel systemd-devel libevdev-devel SDL3-devel fmt-devel glslang-devel
         pugixml-devel enet-devel xxhash-devel bzip2-devel xz-devel libzstd-devel
         zlib-devel minizip-ng-devel lzo-devel lz4-devel libspng-devel cubeb-devel
         libusb1-devel miniupnpc-devel libcurl-devel hidapi-devel gtest-devel
         alsa-lib-devel pulseaudio-libs-devel llvm-devel bluez-libs-devel
         qt6-qtbase-devel qt6-qtbase-private-devel qt6-qtsvg-devel"
    # the distributions lack compatible SFML 3, MbedTLS 2 and libmgba (and
    # Debian minizip-ng): the bundled copies are used, as Dolphin's packages do
    local -a vendored=(-DUSE_SYSTEM_SFML=OFF -DUSE_SYSTEM_MBEDTLS=OFF -DUSE_SYSTEM_LIBMGBA=OFF)
    [[ "$(package_manager)" == "apt" ]] && vendored+=(-DUSE_SYSTEM_MINIZIP-NG=OFF)

    git_clone https://github.com/dolphin-emu/dolphin.git
    # the NoGUI frontend, which games run with, is off by default
    cmake_build -DENABLE_NOGUI=ON -DENABLE_TESTS=OFF "${vendored[@]}"
    cmake_install
    require_executable bin/dolphin-emu
    require_executable bin/dolphin-emu-nogui
    remove_sources
}

installer_main "$@"
