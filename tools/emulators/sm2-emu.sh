#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# sm2-emu (Sega Model 2) installer.
# https://github.com/dmanlfc/sm2-emu
#
# Installs sm2-emu under ${RETROBOX_EMULATORS_DIR}/sm2-emu/app, the prefix the
# Retrobox generator runs it from (bin/sm2-emu + share/sm2-emu/games.xml):
#
#   -i   the tarball of the latest upstream release (x86_64 and aarch64)
#   -s   a build from source (any architecture the toolchain supports)
#   -u   uninstall (the configuration and the saves are kept)
#
# Optional environment variables:
#   SM2_VERSION   release tag to install or build (default: the latest release;
#                 "main" builds the development branch with -s)
#   SM2_GL        OpenGL flavour of a source build: "desktop" (OpenGL 4.3) or
#                 "es" (OpenGL ES 3.1). Default: es on ARM, desktop elsewhere
#   SM2_VULKAN    "ON" (default) or "OFF": build the Vulkan backend
#   SM2_TUNE      -march of a source build (default: native, as the emulator is
#                 bound to the speed of a single core; empty for a portable one)
#   JOBS          parallel build jobs (default: nproc)
#   SM2_KEEP_SRC  "1" keeps the source tree after a build
#
# Created: 30 October 2026
set -euo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
# shellcheck source=../lib/paths.sh
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
# shellcheck source=../lib/log.sh
source "${RETROBOX_ROOT}/tools/lib/log.sh"

readonly GITHUB_REPO="dmanlfc/sm2-emu"
readonly API_URL="https://api.github.com/repos/${GITHUB_REPO}"
readonly SOURCE_UPSTREAM="https://github.com/${GITHUB_REPO}.git"
readonly INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/sm2-emu"
readonly PREFIX_DIR="${INSTALL_DIR}/app"
readonly SRC_ROOT="${RETROBOX_EMULATORS_DIR}/_src"
readonly SM2_SRC="${SRC_ROOT}/sm2-emu"
# read by the generator: which optional backends the binary carries
readonly BUILD_INFO_NAME="retrobox-build.ini"

SM2_VERSION="${SM2_VERSION:-}"
SM2_VULKAN="${SM2_VULKAN:-ON}"
SM2_TUNE="${SM2_TUNE-native}"
JOBS="${JOBS:-$(nproc)}"
SM2_KEEP_SRC="${SM2_KEEP_SRC:-0}"

TMP_DIR=""
SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
    SUDO="sudo"
fi

## FUNCTIONS

# shellcheck disable=SC2329  # called by the EXIT trap
function cleanup() {
    if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi
}
trap cleanup EXIT

function die() {
    log_err "$*"
    exit 1
}

function usage() {
    cat <<EOF
Usage: $(basename "$0") <option>
  -i : install the tarball of the latest sm2-emu release (x86_64, aarch64)
  -s : build sm2-emu from source (see the header of this script for options)
  -u : uninstall sm2-emu (its configuration and saves are kept)
EOF
}

function package_manager() {
    if command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v apt-get &>/dev/null; then
        echo "apt"
    else
        echo "unknown"
    fi
}

# Print the first package of a list that apt knows about (t64 renames...).
function apt_pick() {
    local candidate
    for candidate in "$@"; do
        if apt-cache show "${candidate}" &>/dev/null; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

# Install packages that exist in some releases only, one by one, without failing.
function install_optional() {
    local manager="$1"
    shift
    local package
    for package in "$@"; do
        if [[ "${manager}" == "apt" ]]; then
            ${SUDO} apt-get install -y "${package}" &>/dev/null \
                || log_warn "Optional package ${package} is not available, skipping it."
        else
            ${SUDO} dnf install -y "${package}" &>/dev/null \
                || log_warn "Optional package ${package} is not available, skipping it."
        fi
    done
}

function host_arch() {
    case "$(uname -m)" in
        x86_64 | amd64) echo "x86_64" ;;
        aarch64 | arm64) echo "aarch64" ;;
        *) uname -m ;;
    esac
}

function default_gl_flavour() {
    case "$(host_arch)" in
        aarch64 | arm*) echo "es" ;;
        *) echo "desktop" ;;
    esac
}

# Print the tag of the latest release. The GitHub API answers first; when it
# does not (rate limit, no API access) the highest v* tag of the repository is
# taken, which is how the releases are published.
function latest_tag() {
    local tag
    tag="$(curl -fsSL -H "Accept: application/vnd.github+json" "${API_URL}/releases/latest" 2>/dev/null \
        | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])' 2>/dev/null)" \
        || tag=""
    if [[ -z "${tag}" ]]; then
        tag="$(git ls-remote --tags --refs "${SOURCE_UPSTREAM}" 'v*' 2>/dev/null \
            | awk '{ sub("refs/tags/", "", $2); print $2 }' | sort -V | tail -n 1)" \
            || tag=""
    fi
    [[ -n "${tag}" ]] || return 1
    echo "${tag}"
}

# Print the tag to install or build: SM2_VERSION, or the latest release.
function wanted_tag() {
    if [[ -n "${SM2_VERSION}" ]]; then
        echo "${SM2_VERSION}"
    else
        latest_tag
    fi
}

function write_build_info() {
    local prefix="$1" origin="$2" version="$3" vulkan="$4" gl="$5"
    cat >"${prefix}/${BUILD_INFO_NAME}" <<EOF
# Written by tools/emulators/sm2-emu.sh, read by the Retrobox generator.
[build]
origin = ${origin}
version = ${version}
vulkan = ${vulkan}
opengl = ${gl}
EOF
}

# Swap a freshly installed prefix into place, so a failed install keeps the
# previous one working.
function activate_prefix() {
    local staged="$1"
    [[ -x "${staged}/bin/sm2-emu" ]] || die "No sm2-emu binary in ${staged}/bin"
    [[ -f "${staged}/share/sm2-emu/games.xml" ]] \
        || die "No games.xml in ${staged}/share/sm2-emu"

    mkdir -p "${INSTALL_DIR}"
    rm -rf "${PREFIX_DIR}.old"
    if [[ -d "${PREFIX_DIR}" ]]; then
        mv "${PREFIX_DIR}" "${PREFIX_DIR}.old"
    fi
    mv "${staged}" "${PREFIX_DIR}"
    rm -rf "${PREFIX_DIR}.old"
}

# Check that a prebuilt binary can run here: every library found, and a C and
# C++ runtime as recent as the one of the build machine (Ubuntu 24.04).
function check_runtime_libs() {
    local binary="$1" report missing too_old
    report="$(ldd "${binary}" 2>&1 || true)"
    too_old="$(grep -o "version \`[^']*' not found" <<<"${report}" | sort -u || true)"
    missing="$(awk '/=> not found/ { print $1 }' <<<"${report}" | sort -u || true)"
    if [[ -n "${too_old}" ]]; then
        log_err "The prebuilt sm2-emu needs a newer system: $(tr '\n' ' ' <<<"${too_old}")"
        log_err "Build it from source instead: $(basename "$0") -s"
        return 1
    fi
    if [[ -n "${missing}" ]]; then
        log_err "sm2-emu cannot find these libraries: $(tr '\n' ' ' <<<"${missing}")"
        log_err "Install them with your package manager, or build sm2-emu from source with -s."
        return 1
    fi
    return 0
}

function smoke_test() {
    if timeout 20 "${PREFIX_DIR}/bin/sm2-emu" --list-games &>/dev/null; then
        log_ok "sm2-emu starts and reads its game database."
    else
        log_warn "sm2-emu --list-games failed: check the output of ${PREFIX_DIR}/bin/sm2-emu --help."
    fi
}

function install_runtime_deps() {
    local manager
    manager="$(package_manager)"
    log_info "Installing the runtime libraries of the prebuilt binary..."
    case "${manager}" in
        apt)
            local curl_pkg
            ${SUDO} apt-get update || log_warn "apt-get update failed."
            curl_pkg="$(apt_pick libcurl4t64 libcurl4)" || curl_pkg=""
            ${SUDO} apt-get install -y \
                libharfbuzz0b libfontconfig1 libudev1 \
                libgl1 libegl1 libgles2 libvulkan1 ${curl_pkg:+"${curl_pkg}"} \
                || log_warn "Some runtime libraries could not be installed (apt)."
            ;;
        dnf)
            ${SUDO} dnf install -y \
                libcurl harfbuzz fontconfig systemd-libs \
                mesa-libGL mesa-libEGL mesa-libGLES vulkan-loader \
                || log_warn "Some runtime libraries could not be installed (dnf)."
            ;;
        *)
            log_warn "Unknown package manager: make sure libcurl, harfbuzz, fontconfig, libudev, GL/EGL and the Vulkan loader are installed."
            ;;
    esac
}

function install_tarball() {
    local arch tag url staged extracted
    arch="$(host_arch)"
    if [[ "${arch}" != "x86_64" && "${arch}" != "aarch64" ]]; then
        die "sm2-emu releases are only published for x86_64 and aarch64 (this is ${arch}): use -s to build it"
    fi
    command -v curl &>/dev/null || die "curl is required"
    if [[ "${SM2_VERSION}" == "main" ]]; then
        die "There is no tarball of the main branch: use -s to build it"
    fi

    log_info "Looking for the sm2-emu ${SM2_VERSION:-latest} release..."
    tag="$(wanted_tag)" || die "Could not find the latest sm2-emu release (is the network up?)"
    url="https://github.com/${GITHUB_REPO}/releases/download/${tag}/sm2-emu-${tag}-linux-${arch}.tar.gz"

    TMP_DIR="$(mktemp -d)"
    log_info "Downloading sm2-emu ${tag}: ${url}"
    curl -fL --retry 3 -o "${TMP_DIR}/sm2-emu.tar.gz" "${url}" \
        || die "The download of ${url} failed (does release ${tag} have a ${arch} tarball?)"

    log_info "Extracting..."
    mkdir -p "${TMP_DIR}/extract"
    tar -xzf "${TMP_DIR}/sm2-emu.tar.gz" -C "${TMP_DIR}/extract"
    extracted="$(find "${TMP_DIR}/extract" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "${extracted}" ]] || die "The tarball has an unexpected layout"

    # the release tarballs carry the software renderer, OpenGL (ES on aarch64) and Vulkan
    local gl="desktop"
    if [[ "${arch}" == "aarch64" ]]; then
        gl="es"
    fi
    write_build_info "${extracted}" "tarball" "${tag}" "true" "${gl}"

    install_runtime_deps
    check_runtime_libs "${extracted}/bin/sm2-emu" \
        || die "The prebuilt sm2-emu cannot run on this system (the previous install, if any, is kept)"

    # stage next to the destination, so the swap is a rename on one filesystem
    mkdir -p "${INSTALL_DIR}"
    staged="${INSTALL_DIR}/app.new"
    rm -rf "${staged}"
    mv "${extracted}" "${staged}"
    activate_prefix "${staged}"
    smoke_test
    log_ok "sm2-emu ${tag} installed in ${PREFIX_DIR}."
}

function install_build_deps() {
    local manager
    manager="$(package_manager)"
    log_info "Installing the build dependencies..."
    case "${manager}" in
        apt)
            local curl_dev
            curl_dev="$(apt_pick libcurl4-openssl-dev libcurl4-gnutls-dev)" || curl_dev=""
            ${SUDO} apt-get update
            ${SUDO} apt-get install -y \
                git cmake ninja-build build-essential pkg-config glslc \
                libgl-dev libgles-dev libegl-dev \
                libpugixml-dev ${curl_dev:+"${curl_dev}"} \
                libfontconfig-dev libharfbuzz-dev \
                libx11-dev libxext-dev libxrandr-dev libxcursor-dev \
                libxi-dev libxfixes-dev libxss-dev libxrender-dev libxtst-dev \
                libasound2-dev libpulse-dev libudev-dev \
                libwayland-dev libwayland-bin libxkbcommon-dev libdecor-0-dev \
                || die "Could not install the build dependencies (apt)"
            if [[ "${SM2_VULKAN}" == "ON" ]]; then
                ${SUDO} apt-get install -y libvulkan-dev \
                    || die "Could not install the Vulkan headers (apt); set SM2_VULKAN=OFF to build without them"
            fi
            # SDL 3.2+ from the system when the release has it, the bundled copy otherwise
            install_optional apt libsdl3-dev libvulkan-memory-allocator-dev
            ;;
        dnf)
            ${SUDO} dnf install -y \
                git cmake ninja-build gcc-c++ pkgconf-pkg-config glslc \
                mesa-libGL-devel mesa-libGLES-devel mesa-libEGL-devel \
                pugixml-devel libcurl-devel fontconfig-devel harfbuzz-devel \
                libX11-devel libXext-devel libXrandr-devel libXcursor-devel \
                libXi-devel libXfixes-devel libXScrnSaver-devel libXrender-devel libXtst-devel \
                alsa-lib-devel pulseaudio-libs-devel systemd-devel \
                wayland-devel libxkbcommon-devel libdecor-devel \
                || die "Could not install the build dependencies (dnf)"
            if [[ "${SM2_VULKAN}" == "ON" ]]; then
                ${SUDO} dnf install -y vulkan-loader-devel vulkan-headers \
                    || die "Could not install the Vulkan headers (dnf); set SM2_VULKAN=OFF to build without them"
            fi
            install_optional dnf SDL3-devel
            ;;
        *)
            log_warn "Unknown package manager: install the dependencies listed in BUILDING.md of sm2-emu yourself."
            ;;
    esac
}

function install_source() {
    local ref gl gl_desktop gl_es staged
    if ! ref="$(wanted_tag)"; then
        log_warn "Could not find the latest release, building the main branch."
        ref="main"
    fi
    gl="${SM2_GL:-$(default_gl_flavour)}"
    case "${gl}" in
        desktop) gl_desktop="ON" gl_es="OFF" ;;
        es) gl_desktop="OFF" gl_es="ON" ;;
        *) die "SM2_GL must be 'desktop' or 'es', not '${gl}'" ;;
    esac
    case "${SM2_VULKAN}" in
        ON | OFF) ;;
        *) die "SM2_VULKAN must be ON or OFF, not '${SM2_VULKAN}'" ;;
    esac

    install_build_deps

    log_info "Cloning sm2-emu ${ref} (with its submodules, this takes a while)..."
    mkdir -p "${SRC_ROOT}"
    rm -rf "${SM2_SRC}"
    git clone --depth 1 --branch "${ref}" --recurse-submodules --shallow-submodules \
        "${SOURCE_UPSTREAM}" "${SM2_SRC}" \
        || die "Could not clone ${SOURCE_UPSTREAM} at ${ref}"

    log_info "Configuring (arch: $(host_arch), OpenGL: ${gl}, Vulkan: ${SM2_VULKAN}, tune: ${SM2_TUNE:-none})..."
    cmake -S "${SM2_SRC}" -B "${SM2_SRC}/build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DSM2_BUILD_TESTS=OFF \
        -DSM2_LTO=ON \
        -DSM2_TUNE="${SM2_TUNE}" \
        -DSM2_BUILD_VULKAN="${SM2_VULKAN}" \
        -DSM2_BUILD_OPENGL_DESKTOP="${gl_desktop}" \
        -DSM2_BUILD_OPENGL_ES="${gl_es}" \
        || die "CMake could not configure sm2-emu: check the messages above"

    log_info "Building with ${JOBS} jobs..."
    cmake --build "${SM2_SRC}/build" -j "${JOBS}" \
        || die "The build failed: check the messages above (lower JOBS if the linker ran out of memory)"

    mkdir -p "${INSTALL_DIR}"
    staged="${INSTALL_DIR}/app.new"
    rm -rf "${staged}"
    cmake --install "${SM2_SRC}/build" --prefix "${staged}" \
        || die "cmake --install failed"

    local vulkan="false"
    if [[ "${SM2_VULKAN}" == "ON" ]]; then
        vulkan="true"
    fi
    write_build_info "${staged}" "source" "${ref}" "${vulkan}" "${gl}"
    activate_prefix "${staged}"

    if [[ "${SM2_KEEP_SRC}" == "1" ]]; then
        log_info "Source tree kept in ${SM2_SRC}."
    else
        rm -rf "${SM2_SRC}"
        rmdir "${SRC_ROOT}" 2>/dev/null || true
    fi

    smoke_test
    log_ok "sm2-emu ${ref} built and installed in ${PREFIX_DIR}."
}

function uninstall() {
    if [[ ! -d "${INSTALL_DIR}" ]]; then
        log_info "sm2-emu is not installed."
        return 0
    fi
    rm -rf "${INSTALL_DIR}"
    log_ok "sm2-emu uninstalled. Its configuration (${RETROBOX_EMUCONFIG_DIR}/sm2-emu) and saves are kept."
}

## MAIN

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

# setup.sh reads the flags of this dispatch block: keep it as `case "$1" in`
case "$1" in
    "-i") install_tarball ;;
    "-s") install_source ;;
    "-u" | "-d") uninstall ;;
    *)
        usage
        exit 1
        ;;
esac

exit 0
