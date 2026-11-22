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
    # What the build asks for and what it links (ruby/cmake/os-linux.cmake and
    # hiro/cmake/os-linux.cmake): find_package(X11 REQUIRED) and its X11::Xrandr
    # target, which cmake makes carry X11::Xrender, X11::Xext and X11::X11;
    # find_package(OpenGL REQUIRED) for OpenGL::GLX (libGLX and libOpenGL, both
    # of libgl-dev); find_package(GTK) for the GTK3 interface; SDL3 for the
    # audio and the joypads.
    # libxrandr-dev and libxrender-dev were missing: without the first,
    # configure stops at "X11::Xrandr ... but the target was not found".
    # libice-dev and libglu1-mesa-dev were asked for by mistake: no ICE header
    # is included anywhere and GLU is not used.
    install_packages \
        "build-essential cmake ninja-build git pkg-config libsdl3-dev libgtk-3-dev
         libx11-dev libxext-dev libxrandr-dev libxrender-dev libgl-dev" \
        "gcc-c++ cmake ninja-build git pkgconf-pkg-config SDL3-devel gtk3-devel
         libX11-devel libXext-devel libXrandr-devel libXrender-devel
         mesa-libGL-devel"
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
