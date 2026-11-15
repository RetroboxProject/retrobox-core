#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Keisho (Sega Model 1, 2 & 3) installer.
# https://github.com/Keisho-Emu/Keisho
#
# Installs Keisho under ${RETROBOX_EMULATORS_DIR}/keisho/app, the prefix the
# Retrobox generator runs it from (bin/keisho + share/keisho/games.xml):
#
#   -i   the tarball of the latest upstream release (x86_64 and aarch64)
#   -s   a build from source (any architecture the toolchain supports)
#   -u   uninstall (the configuration and the saves are kept)
#
# Optional environment variables:
#   KEISHO_VERSION   release tag to install or build (default: the latest release;
#                 "main" builds the development branch with -s)
#   KEISHO_GL        OpenGL flavour of a source build: "desktop" (OpenGL 4.3) or
#                 "es" (OpenGL ES 3.1). Default: es on ARM, desktop elsewhere
#   KEISHO_VULKAN    "ON" (default) or "OFF": build the Vulkan backend
#   KEISHO_TUNE      -march of a source build (default: native, as the emulator is
#                 bound to the speed of a single core; empty for a portable one)
#   JOBS          parallel build jobs (default: nproc)
#   KEISHO_KEEP_SRC  "1" keeps the source tree after a build
#
# Created: 30 October 2026
set -euo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
# shellcheck source=../lib/paths.sh
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
# shellcheck source=../lib/log.sh
source "${RETROBOX_ROOT}/tools/lib/log.sh"

readonly GITHUB_REPO="Keisho-Emu/Keisho"
readonly API_URL="https://api.github.com/repos/${GITHUB_REPO}"
readonly SOURCE_UPSTREAM="https://github.com/${GITHUB_REPO}.git"
readonly INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/keisho"
readonly PREFIX_DIR="${INSTALL_DIR}/app"
# the name before the project was renamed: its install is replaced by this one
readonly LEGACY_INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/sm2-emu"
readonly SRC_ROOT="${RETROBOX_EMULATORS_DIR}/_src"
readonly KEISHO_SRC="${SRC_ROOT}/keisho"
# read by the generator: which optional backends the binary carries
readonly BUILD_INFO_NAME="retrobox-build.ini"

KEISHO_VERSION="${KEISHO_VERSION:-}"
KEISHO_VULKAN="${KEISHO_VULKAN:-ON}"
KEISHO_TUNE="${KEISHO_TUNE-native}"
JOBS="${JOBS:-$(nproc)}"
KEISHO_KEEP_SRC="${KEISHO_KEEP_SRC:-0}"

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
  -i : install the tarball of the latest Keisho release (x86_64, aarch64)
  -s : build Keisho from source (see the header of this script for options)
  -u : uninstall Keisho (its configuration and saves are kept)
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

# Print the tag to install or build: KEISHO_VERSION, or the latest release.
function wanted_tag() {
    if [[ -n "${KEISHO_VERSION}" ]]; then
        echo "${KEISHO_VERSION}"
    else
        latest_tag
    fi
}

function write_build_info() {
    local prefix="$1" origin="$2" version="$3" vulkan="$4" gl="$5"
    cat >"${prefix}/${BUILD_INFO_NAME}" <<EOF
# Written by tools/emulators/keisho.sh, read by the Retrobox generator.
[build]
origin = ${origin}
version = ${version}
vulkan = ${vulkan}
opengl = ${gl}
EOF
}

# Remove the install of sm2-emu, the former name of Keisho. Its configuration
# and saves are not here: the generator moves them the first time it runs.
function remove_legacy_install() {
    if [[ -d "${LEGACY_INSTALL_DIR}" ]]; then
        rm -rf "${LEGACY_INSTALL_DIR}"
        log_info "The former sm2-emu install was removed."
    fi
}

# Swap a freshly installed prefix into place, so a failed install keeps the
# previous one working.
function activate_prefix() {
    local staged="$1"
    [[ -x "${staged}/bin/keisho" ]] || die "No Keisho binary in ${staged}/bin"
    [[ -f "${staged}/share/keisho/games.xml" ]] \
        || die "No games.xml in ${staged}/share/keisho"

    mkdir -p "${INSTALL_DIR}"
    rm -rf "${PREFIX_DIR}.old"
    if [[ -d "${PREFIX_DIR}" ]]; then
        mv "${PREFIX_DIR}" "${PREFIX_DIR}.old"
    fi
    mv "${staged}" "${PREFIX_DIR}"
    rm -rf "${PREFIX_DIR}.old"
    remove_legacy_install
}

# Check that a prebuilt binary can run here: every library found, and a C and
# C++ runtime as recent as the one of the build machine (Ubuntu 24.04).
function check_runtime_libs() {
    local binary="$1" report missing too_old
    report="$(ldd "${binary}" 2>&1 || true)"
    too_old="$(grep -o "version \`[^']*' not found" <<<"${report}" | sort -u || true)"
    missing="$(awk '/=> not found/ { print $1 }' <<<"${report}" | sort -u || true)"
    if [[ -n "${too_old}" ]]; then
        log_err "The prebuilt Keisho needs a newer system: $(tr '\n' ' ' <<<"${too_old}")"
        log_err "Build it from source instead: $(basename "$0") -s"
        return 1
    fi
    if [[ -n "${missing}" ]]; then
        log_err "keisho cannot find these libraries: $(tr '\n' ' ' <<<"${missing}")"
        log_err "Install them with your package manager, or build Keisho from source with -s."
        return 1
    fi
    return 0
}

function smoke_test() {
    if timeout 20 "${PREFIX_DIR}/bin/keisho" --list-games &>/dev/null; then
        log_ok "keisho starts and reads its game database."
    else
        log_warn "keisho --list-games failed: check the output of ${PREFIX_DIR}/bin/keisho --help."
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
        die "Keisho releases are only published for x86_64 and aarch64 (this is ${arch}): use -s to build it"
    fi
    command -v curl &>/dev/null || die "curl is required"
    if [[ "${KEISHO_VERSION}" == "main" ]]; then
        die "There is no tarball of the main branch: use -s to build it"
    fi

    log_info "Looking for the Keisho ${KEISHO_VERSION:-latest} release..."
    tag="$(wanted_tag)" || die "Could not find the latest Keisho release (is the network up?)"
    url="https://github.com/${GITHUB_REPO}/releases/download/${tag}/keisho-${tag}-linux-${arch}.tar.gz"

    TMP_DIR="$(mktemp -d)"
    log_info "Downloading Keisho ${tag}: ${url}"
    curl -fL --retry 3 -o "${TMP_DIR}/keisho.tar.gz" "${url}" \
        || die "The download of ${url} failed (does release ${tag} have a ${arch} tarball?)"

    log_info "Extracting..."
    mkdir -p "${TMP_DIR}/extract"
    tar -xzf "${TMP_DIR}/keisho.tar.gz" -C "${TMP_DIR}/extract"
    extracted="$(find "${TMP_DIR}/extract" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "${extracted}" ]] || die "The tarball has an unexpected layout"

    # the release tarballs carry the software renderer, OpenGL (ES on aarch64) and Vulkan
    local gl="desktop"
    if [[ "${arch}" == "aarch64" ]]; then
        gl="es"
    fi
    write_build_info "${extracted}" "tarball" "${tag}" "true" "${gl}"

    install_runtime_deps
    check_runtime_libs "${extracted}/bin/keisho" \
        || die "The prebuilt Keisho cannot run on this system (the previous install, if any, is kept)"

    # stage next to the destination, so the swap is a rename on one filesystem
    mkdir -p "${INSTALL_DIR}"
    staged="${INSTALL_DIR}/app.new"
    rm -rf "${staged}"
    mv "${extracted}" "${staged}"
    activate_prefix "${staged}"
    smoke_test
    log_ok "keisho ${tag} installed in ${PREFIX_DIR}."
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
            if [[ "${KEISHO_VULKAN}" == "ON" ]]; then
                ${SUDO} apt-get install -y libvulkan-dev \
                    || die "Could not install the Vulkan headers (apt); set KEISHO_VULKAN=OFF to build without them"
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
            if [[ "${KEISHO_VULKAN}" == "ON" ]]; then
                ${SUDO} dnf install -y vulkan-loader-devel vulkan-headers \
                    || die "Could not install the Vulkan headers (dnf); set KEISHO_VULKAN=OFF to build without them"
            fi
            install_optional dnf SDL3-devel
            ;;
        *)
            log_warn "Unknown package manager: install the dependencies listed in BUILDING.md of Keisho yourself."
            ;;
    esac
}

function install_source() {
    local ref gl gl_desktop gl_es staged
    if ! ref="$(wanted_tag)"; then
        log_warn "Could not find the latest release, building the main branch."
        ref="main"
    fi
    gl="${KEISHO_GL:-$(default_gl_flavour)}"
    case "${gl}" in
        desktop) gl_desktop="ON" gl_es="OFF" ;;
        es) gl_desktop="OFF" gl_es="ON" ;;
        *) die "KEISHO_GL must be 'desktop' or 'es', not '${gl}'" ;;
    esac
    case "${KEISHO_VULKAN}" in
        ON | OFF) ;;
        *) die "KEISHO_VULKAN must be ON or OFF, not '${KEISHO_VULKAN}'" ;;
    esac

    install_build_deps

    log_info "Cloning Keisho ${ref} (with its submodules, this takes a while)..."
    mkdir -p "${SRC_ROOT}"
    rm -rf "${KEISHO_SRC}"
    git clone --depth 1 --branch "${ref}" --recurse-submodules --shallow-submodules \
        "${SOURCE_UPSTREAM}" "${KEISHO_SRC}" \
        || die "Could not clone ${SOURCE_UPSTREAM} at ${ref}"

    log_info "Configuring (arch: $(host_arch), OpenGL: ${gl}, Vulkan: ${KEISHO_VULKAN}, tune: ${KEISHO_TUNE:-none})..."
    cmake -S "${KEISHO_SRC}" -B "${KEISHO_SRC}/build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DSM2_BUILD_TESTS=OFF \
        -DSM2_LTO=ON \
        -DSM2_TUNE="${KEISHO_TUNE}" \
        -DSM2_BUILD_VULKAN="${KEISHO_VULKAN}" \
        -DSM2_BUILD_OPENGL_DESKTOP="${gl_desktop}" \
        -DSM2_BUILD_OPENGL_ES="${gl_es}" \
        || die "CMake could not configure Keisho: check the messages above"

    log_info "Building with ${JOBS} jobs..."
    cmake --build "${KEISHO_SRC}/build" -j "${JOBS}" \
        || die "The build failed: check the messages above (lower JOBS if the linker ran out of memory)"

    mkdir -p "${INSTALL_DIR}"
    staged="${INSTALL_DIR}/app.new"
    rm -rf "${staged}"
    cmake --install "${KEISHO_SRC}/build" --prefix "${staged}" \
        || die "cmake --install failed"

    local vulkan="false"
    if [[ "${KEISHO_VULKAN}" == "ON" ]]; then
        vulkan="true"
    fi
    write_build_info "${staged}" "source" "${ref}" "${vulkan}" "${gl}"
    activate_prefix "${staged}"

    if [[ "${KEISHO_KEEP_SRC}" == "1" ]]; then
        log_info "Source tree kept in ${KEISHO_SRC}."
    else
        rm -rf "${KEISHO_SRC}"
        rmdir "${SRC_ROOT}" 2>/dev/null || true
    fi

    smoke_test
    log_ok "Keisho ${ref} built and installed in ${PREFIX_DIR}."
}

function uninstall() {
    remove_legacy_install
    if [[ ! -d "${INSTALL_DIR}" ]]; then
        log_info "Keisho is not installed."
        return 0
    fi
    rm -rf "${INSTALL_DIR}"
    log_ok "Keisho uninstalled. Its configuration (${RETROBOX_EMUCONFIG_DIR}/keisho) and saves are kept."
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
