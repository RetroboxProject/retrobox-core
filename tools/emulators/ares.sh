#!/usr/bin/env bash
# ares (multi-system), built from source with librashader for its shaders.
# librashader needs Rust 1.88 or newer: the system's if it is recent enough
# (Debian 13 ships 1.85), else rustup's, installed for Retrobox if missing.
EMULATOR="ares"
LABEL="ares"
# the layout before app/
LEGACY=(bin lib share)
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

RUST_MIN="1.88"
# where a rustup of Retrobox's own lives, kept between updates
RUST_DIR="${RETROBOX_EMULATORS_DIR}/_src/rust"

# rust_recent: succeed when the cargo and rustc on PATH are at least RUST_MIN.
function rust_recent() {
    local version
    command -v cargo &>/dev/null || return 1
    version="$(rustc --version 2>/dev/null | awk '{print $2}')"
    [[ -n "${version}" ]] || return 1
    [[ "$(printf '%s\n%s\n' "${RUST_MIN}" "${version}" | sort -V | head -n 1)" == "${RUST_MIN}" ]]
}

# use_rust: put a recent enough Rust toolchain on PATH, installing one with
# rustup under ${RUST_DIR} (nothing outside it is touched) when there is none.
function use_rust() {
    rust_recent && return 0
    if [[ -x "${HOME}/.cargo/bin/rustup" ]]; then
        export PATH="${HOME}/.cargo/bin:${PATH}"
        rustup toolchain install stable --profile minimal || die "rustup could not install Rust"
        rustup default stable >/dev/null
        rust_recent && return 0
    fi
    export RUSTUP_HOME="${RUST_DIR}/rustup" CARGO_HOME="${RUST_DIR}/cargo"
    export PATH="${CARGO_HOME}/bin:${PATH}"
    if [[ ! -x "${CARGO_HOME}/bin/rustup" ]]; then
        log_info "Installing Rust (rustup) into ${RUST_DIR}..."
        mkdir -p "${RUST_DIR}"
        curl -fsSL --retry 3 https://sh.rustup.rs -o "${TMP_DIR}/rustup-init.sh" \
            || die "Could not download rustup (network down?)"
        sh "${TMP_DIR}/rustup-init.sh" -y --no-modify-path --profile minimal \
            --default-toolchain stable || die "rustup could not install Rust"
    else
        rustup update stable || log_warn "rustup could not update Rust: using the one it has"
    fi
    rust_recent || die "librashader needs Rust ${RUST_MIN} or newer"
}

function build_librashader() {
    use_rust
    local source="${TMP_DIR}/librashader" library profile="${LIBRASHADER_PROFILE:-optimized}"
    git clone --depth 1 https://github.com/SnowflakePowered/librashader.git "${source}" \
        || die "Could not clone librashader"
    log_info "Building librashader with $(rustc --version)..."
    (cd "${source}" && CARGO_BUILD_JOBS="${JOBS}" \
        cargo run -p librashader-build-script -- --profile "${profile}") \
        || die "The librashader build failed (LIBRASHADER_PROFILE=release needs less memory)"
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
        "build-essential cmake ninja-build git curl pkg-config libsdl3-dev libgtk-3-dev
         libx11-dev libxext-dev libxrandr-dev libxrender-dev libgl-dev" \
        "gcc-c++ cmake ninja-build git curl pkgconf-pkg-config SDL3-devel gtk3-devel
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
