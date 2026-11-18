#!/usr/bin/env bash
# ares (multi-system), built from source with librashader for its shaders.
# librashader needs a nightly Rust toolchain (https://rustup.rs).
EMULATOR="ares"
LABEL="ares"
# the layout before app/
LEGACY=(bin lib share)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

function build_librashader() {
    command -v rustup &>/dev/null \
        || die "librashader needs a nightly Rust toolchain: install rustup (https://rustup.rs) and run this again"
    rustup toolchain list | grep -q '^nightly' || rustup toolchain install nightly
    local source="${TMP_DIR}/librashader" library
    git clone --depth 1 https://github.com/SnowflakePowered/librashader.git "${source}" \
        || die "Could not clone librashader"
    log_info "Building librashader..."
    (cd "${source}" && rustup run nightly cargo run -p librashader-build-script -- --profile optimized) \
        || die "The librashader build failed"
    library="$(find "${source}/target" -maxdepth 2 -type f -name librashader.so | head -n 1)"
    [[ -n "${library}" ]] || die "The librashader build produced no librashader.so"
    mkdir -p "${STAGE}/lib"
    cp "${library}" "${STAGE}/lib/librashader.so"
}

function install_source() {
    install_packages \
        "build-essential cmake ninja-build git pkg-config libsdl3-dev libgtk-3-dev
         libx11-dev libxext-dev libice-dev libgl-dev libglu1-mesa-dev" \
        "gcc-c++ cmake ninja-build git pkgconf-pkg-config SDL3-devel gtk3-devel
         libX11-devel libXext-devel libICE-devel mesa-libGL-devel mesa-libGLU-devel"
    git_clone https://github.com/ares-emulator/ares.git
    cmake_build
    cmake_install
    # older CMake files left the binaries out of the install
    local binary found
    for binary in ares sourcery; do
        [[ -x "${STAGE}/bin/${binary}" ]] && continue
        found="$(find "${SRC_DIR}/build" -maxdepth 4 -type f -name "${binary}" -perm -u+x | head -n 1)"
        [[ -n "${found}" ]] && install -D "${found}" "${STAGE}/bin/${binary}"
    done
    require_executable bin/ares
    build_librashader
    remove_sources
}

installer_main "$@"
