#!/usr/bin/env bash
# Keisho (Sega Model 1, 2 and 3): https://github.com/Keisho-Emu/Keisho
# The tarball of the latest release (x86_64, aarch64), or a build from source.
# The prefix it installs (app/: bin/keisho, share/keisho/games.xml) is the one
# the Retrobox generator runs it from.
#
#   KEISHO_VERSION   release tag to install or build (default: the latest;
#                    "main" builds the development branch)
#   KEISHO_GL        OpenGL flavour of a source build: "desktop" (OpenGL 4.3)
#                    or "es" (OpenGL ES 3.1). Default: es on ARM, desktop elsewhere
#   KEISHO_VULKAN    ON (default) or OFF: build the Vulkan backend
#   KEISHO_TUNE      -march of a source build (default: native, the emulator is
#                    bound to the speed of one core; empty for a portable build)
EMULATOR="keisho"
LABEL="Keisho"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly REPOSITORY="Keisho-Emu/Keisho"
readonly UPSTREAM="https://github.com/${REPOSITORY}.git"
# its install under its former name, which this one replaces
readonly FORMER_INSTALL="${RETROBOX_EMULATORS_DIR}/sm2-emu"
# read by the generator: which optional backends the binary carries
readonly BUILD_INFO="retrobox-build.ini"

KEISHO_VERSION="${KEISHO_VERSION:-}"
KEISHO_VULKAN="${KEISHO_VULKAN:-ON}"
KEISHO_TUNE="${KEISHO_TUNE-native}"

function default_gl() {
    [[ "${ARCH}" == "x86_64" ]] && echo "desktop" || echo "es"
}

# The tag to install: KEISHO_VERSION, else the latest release (from the API,
# or the highest v* tag when the API does not answer).
function wanted_tag() {
    if [[ -n "${KEISHO_VERSION}" ]]; then
        echo "${KEISHO_VERSION}"
        return 0
    fi
    local tag
    tag="$(curl -fsSL "https://api.github.com/repos/${REPOSITORY}/releases/latest" 2>/dev/null \
        | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])' 2>/dev/null)" \
        || tag=""
    if [[ -z "${tag}" ]]; then
        tag="$(git ls-remote --tags --refs "${UPSTREAM}" 'v*' 2>/dev/null \
            | awk '{ sub("refs/tags/", "", $2); print $2 }' | sort -V | tail -n 1)" || tag=""
    fi
    [[ -n "${tag}" ]] || return 1
    echo "${tag}"
}

function write_build_info() {
    local origin="$1" version="$2" vulkan="$3" gl="$4"
    cat >"${STAGE}/${BUILD_INFO}" <<INFO
# Written by tools/emulators/keisho.sh, read by the Retrobox generator.
[build]
origin = ${origin}
version = ${version}
vulkan = ${vulkan}
opengl = ${gl}
INFO
}

function check_install() {
    require_executable bin/keisho
    [[ -f "${STAGE}/share/keisho/games.xml" ]] || die "The install has no share/keisho/games.xml"
}

# A prebuilt binary runs only with every library found, and a C/C++ runtime as
# recent as the build machine's (Ubuntu 24.04).
function check_runtime_libs() {
    local report missing too_old
    report="$(ldd "${STAGE}/bin/keisho" 2>&1 || true)"
    too_old="$(grep -o "version \`[^']*' not found" <<<"${report}" | sort -u || true)"
    missing="$(awk '/=> not found/ { print $1 }' <<<"${report}" | sort -u || true)"
    if [[ -n "${too_old}" ]]; then
        die "The prebuilt Keisho needs a newer system ($(tr '\n' ' ' <<<"${too_old}")): build it with -s"
    fi
    if [[ -n "${missing}" ]]; then
        die "keisho cannot find $(tr '\n' ' ' <<<"${missing}"): install them, or build it with -s"
    fi
}

function install_archive() {
    case "${ARCH}" in
        x86_64 | aarch64) ;;
        *) unavailable "Keisho releases are only built for x86_64 and aarch64." ;;
    esac
    [[ "${KEISHO_VERSION}" != "main" ]] || unavailable "There is no tarball of the main branch."
    local tag
    tag="$(wanted_tag)" || die "Could not find the latest Keisho release (is the network up?)"
    fetch "https://github.com/${REPOSITORY}/releases/download/${tag}/keisho-${tag}-linux-${ARCH}.tar.gz" \
        "${TMP_DIR}/keisho.tar.gz"
    extract_archive "${TMP_DIR}/keisho.tar.gz" "${STAGE}"
    check_install
    # the release tarballs carry the software renderer, OpenGL (ES on ARM) and Vulkan
    write_build_info tarball "${tag}" true "$(default_gl)"
    install_packages \
        "libharfbuzz0b libfontconfig1 libudev1 libgl1 libegl1 libgles2 libvulkan1 libcurl4t64|libcurl4" \
        "libcurl harfbuzz fontconfig systemd-libs mesa-libGL mesa-libEGL mesa-libGLES vulkan-loader"
    check_runtime_libs
}

function install_source() {
    local ref gl gl_desktop gl_es vulkan="false"
    ref="$(wanted_tag)" || { log_warn "No release found, building the main branch."; ref="main"; }
    gl="${KEISHO_GL:-$(default_gl)}"
    case "${gl}" in
        desktop) gl_desktop="ON" gl_es="OFF" ;;
        es) gl_desktop="OFF" gl_es="ON" ;;
        *) die "KEISHO_GL must be 'desktop' or 'es', not '${gl}'" ;;
    esac
    case "${KEISHO_VULKAN}" in
        ON) vulkan="true" ;;
        OFF) ;;
        *) die "KEISHO_VULKAN must be ON or OFF, not '${KEISHO_VULKAN}'" ;;
    esac
    install_packages \
        "git cmake ninja-build build-essential pkg-config glslc libgl-dev libgles-dev
         libegl-dev libpugixml-dev libcurl4-openssl-dev|libcurl4-gnutls-dev
         libfontconfig-dev libharfbuzz-dev libx11-dev libxext-dev libxrandr-dev
         libxcursor-dev libxi-dev libxfixes-dev libxss-dev libxrender-dev libxtst-dev
         libasound2-dev libpulse-dev libudev-dev libwayland-dev libwayland-bin
         libxkbcommon-dev libdecor-0-dev libsdl3-dev libvulkan-dev
         libvulkan-memory-allocator-dev" \
        "git cmake ninja-build gcc-c++ pkgconf-pkg-config glslc mesa-libGL-devel
         mesa-libGLES-devel mesa-libEGL-devel pugixml-devel libcurl-devel
         fontconfig-devel harfbuzz-devel libX11-devel libXext-devel libXrandr-devel
         libXcursor-devel libXi-devel libXfixes-devel libXScrnSaver-devel
         libXrender-devel libXtst-devel alsa-lib-devel pulseaudio-libs-devel
         systemd-devel wayland-devel libxkbcommon-devel libdecor-devel SDL3-devel
         vulkan-loader-devel vulkan-headers"
    git_clone "${UPSTREAM}" "${ref}"
    log_info "OpenGL: ${gl}, Vulkan: ${KEISHO_VULKAN}, tune: ${KEISHO_TUNE:-none}"
    cmake_build -DSM2_BUILD_TESTS=OFF -DSM2_LTO=ON -DSM2_TUNE="${KEISHO_TUNE}" \
        -DSM2_BUILD_VULKAN="${KEISHO_VULKAN}" -DSM2_BUILD_OPENGL_DESKTOP="${gl_desktop}" \
        -DSM2_BUILD_OPENGL_ES="${gl_es}"
    cmake_install
    check_install
    write_build_info source "${ref}" "${vulkan}" "${gl}"
    remove_sources
}

function remove_former_install() {
    if [[ -d "${FORMER_INSTALL}" ]]; then
        rm -rf "${FORMER_INSTALL}"
        log_info "Removed the former sm2-emu install."
    fi
}

function after_install() {
    remove_former_install
    if timeout 20 "${APP_DIR}/bin/keisho" --list-games &>/dev/null; then
        log_ok "keisho starts and reads its game database."
    else
        log_warn "keisho --list-games failed: check ${APP_DIR}/bin/keisho --help."
    fi
}

function before_uninstall() {
    remove_former_install
}

installer_main "$@"
