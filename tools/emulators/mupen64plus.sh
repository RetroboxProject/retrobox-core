#!/usr/bin/env bash
# Mupen64Plus (Nintendo 64), standalone: a build from source of the console
# frontend, the core and the plugins that batocera ships. Each part is built at
# the version batocera pins for it, with the patches batocera applies to it (the
# states and saves named after the ROM, no start message...), and with Retrobox's
# own (patches/mupen64plus: Glide64mk2's RenderHeight, overscan and WaitForGPU). On
# x86_64 the core uses the new dynamic recompiler, as on ARM: the old one loops on
# some games (1080 Snowboarding fills the memory until the system kills it).
#
# It builds on x86_64 and on aarch64. With MUPEN64PLUS_GL=gles the build only needs
# OpenGL ES and EGL: it does not need the desktop OpenGL (libGL, GLU), nor the
# development files of X11 or of Wayland, so it works the same on a board that runs
# a bare KMS/DRM session (SDL2's kmsdrm video driver), on X11 or on Wayland. What
# decides the window system at run time is the SDL2 of the system, not this build.
#
#   MUPEN64PLUS_CFLAGS        optimization flags of the build (default:
#                             -O3 -march=native -pipe, for the machine it is built on)
#   MUPEN64PLUS_GL            the OpenGL API the build uses: gl (desktop OpenGL, the
#                             default) or gles (OpenGL ES through EGL, as batocera
#                             builds it on ARM boards). With gles the core's on-screen
#                             display, Glide64mk2 and Rice are built with USE_GLES=1
#                             and GLideN64 with EGL (it needs OpenGL ES 3.0). Glide64mk2
#                             on OpenGL ES ignores Retrobox's RenderHeight, overscan and
#                             WaitForGPU options, which only exist in its desktop path
#   MUPEN64PLUS_BATOCERA_REF  batocera.linux branch, tag or commit to read the versions
#                             and the patches from (default: master)
#   MUPEN64PLUS_<PART>_REF    commit or tag of one part, instead of batocera's. PART is
#                             CORE, UI_CONSOLE, AUDIO_SDL, INPUT_SDL, RSP_HLE,
#                             VIDEO_GLIDE64MK2, VIDEO_RICE or GLIDEN64
EMULATOR="mupen64plus"
LABEL="Mupen64Plus"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"


BATOCERA_REF="${MUPEN64PLUS_BATOCERA_REF:-master}"
BATOCERA_PACKAGES="package/batocera/emulators/mupen64plus"
BATOCERA_RAW="https://raw.githubusercontent.com/batocera-linux/batocera.linux/${BATOCERA_REF}/${BATOCERA_PACKAGES}"
BATOCERA_API="https://api.github.com/repos/batocera-linux/batocera.linux/contents/${BATOCERA_PACKAGES}"
OWN_PATCHES="$(dirname "$(readlink -f "$0")")/patches/mupen64plus"
# gl or gles: checked by install_source, so that -u and -l work whatever it holds
GL_API="${MUPEN64PLUS_GL:-gl}"
# the parts with a Makefile of their own, in the order they are built: the core
# goes first, the others are compiled against its headers
MAKE_PARTS=(core ui_console audio_sdl input_sdl rsp_hle video_glide64mk2 video_rice)


# is_arm64: whether this is a 64-bit ARM machine (uname says aarch64, or arm64 on
# some systems).
function is_arm64() {
    [[ "${ARCH}" == "aarch64" || "${ARCH}" == "arm64" ]]
}


# package_of <part>: the name of the part in batocera (mupen64plus-video-rice...).
function package_of() {
    echo "mupen64plus-${1//_/-}"
}


# repository_of <part>: the upstream repository of the part.
function repository_of() {
    case "$1" in
        gliden64) echo "https://github.com/gonetz/GLideN64.git" ;;
        *) echo "https://github.com/mupen64plus/$(package_of "$1").git" ;;
    esac
}


# batocera_version <part>: the commit batocera builds the part from (nothing when
# its package file cannot be read).
function batocera_version() {
    local package
    package="$(package_of "$1")"
    curl -fsSL --retry 3 "${BATOCERA_RAW}/${package}/${package}.mk" 2>/dev/null |
        sed -n 's/^[A-Z0-9_]*_VERSION[[:space:]]*=[[:space:]]*\([^[:space:]]*\).*/\1/p' |
        head -n 1 || true
}


# apply_batocera_patches <part> <folder>: the patches batocera has for the part.
# Its mupeninifile patch is left out: it hardcodes /usr/share/mupen64plus, and
# Retrobox starts the emulator with --datadir.
function apply_batocera_patches() {
    local package json listing patch
    local -a headers=()
    package="$(package_of "$1")"
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        headers+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    if ! json="$(curl -fsSL --retry 3 "${headers[@]}" "${BATOCERA_API}/${package}?ref=${BATOCERA_REF}")"; then
        log_warn "Could not read the patches of ${package} in batocera: building it without them."
        return 0
    fi
    listing="$(python3 -I -c '
import json, sys
for entry in sorted(json.load(sys.stdin), key=lambda item: item["name"]):
    if entry["name"].endswith(".patch"):
        print(entry["name"])
' <<<"${json}")"
    while IFS= read -r patch; do
        case "${patch}" in
            "" | *mupeninifile*) continue ;;
        esac
        fetch "${BATOCERA_RAW}/${package}/${patch}" "${TMP_DIR}/${patch}"
        git -C "$2" apply "${TMP_DIR}/${patch}" \
            || die "batocera's ${patch} does not apply to ${package}"
        log_info "Applied ${patch}."
    done <<<"${listing}"
}


# apply_own_patches <part> <folder>: Retrobox's patches for the part, after
# batocera's (patches/mupen64plus/<part>/*.patch, next to this script).
function apply_own_patches() {
    local patch
    for patch in "${OWN_PATCHES}/$1"/*.patch; do
        [[ -f "${patch}" ]] || continue
        git -C "$2" apply "${patch}" \
            || die "$(basename "${patch}") does not apply to $(package_of "$1")"
        log_info "Applied $(basename "${patch}")."
    done
}


# fetch_part <part> <folder>: the source of the part at the commit batocera builds it
# from (or the one MUPEN64PLUS_<PART>_REF names), with batocera's patches and
# Retrobox's applied.
function fetch_part() {
    local part="$1" folder="$2" override ref
    override="MUPEN64PLUS_${part^^}_REF"
    ref="${!override:-}"
    [[ -n "${ref}" ]] || ref="$(batocera_version "${part}")"
    if [[ -z "${ref}" ]]; then
        log_warn "batocera gives no version for ${part}: using the default branch of upstream."
    fi
    log_info "Fetching $(package_of "${part}")${ref:+ (${ref})}..."
    rm -rf "${folder}"
    mkdir -p "${folder}"
    git -C "${folder}" init -q
    git -C "${folder}" remote add origin "$(repository_of "${part}")"
    git -C "${folder}" fetch -q --depth 1 origin "${ref:-HEAD}" \
        || die "Could not fetch ${part} (${ref:-HEAD})"
    git -C "${folder}" checkout -q FETCH_HEAD || die "Could not check out ${part}"
    apply_batocera_patches "${part}" "${folder}"
    apply_own_patches "${part}" "${folder}"
}


# make_part <part> <flags> [VARIABLE=value...]: build a part with its Makefile,
# installed in ${STAGE}; the variables go to make.
function make_part() {
    local part="$1" flags="$2"
    local -a args=(
        -C "${SRC_DIR}/${part}/projects/unix"
        PREFIX="${STAGE}" APIDIR="${SRC_DIR}/core/src/api"
        OPTFLAGS="${flags}" VULKAN=0 "${@:3}"
    )
    log_info "Building $(package_of "${part}") with ${JOBS} jobs..."
    make "${args[@]}" all -j "${JOBS}" \
        || die "The build of ${part} failed (lower JOBS if the linker ran out of memory)"
    make "${args[@]}" install || die "Could not install ${part}"
}


# check_gles: the OpenGL ES build needs the development files of glesv2 and egl
# (found by pkg-config), with the OpenGL ES 3.0 header GLideN64 includes. Nothing
# of X11 or Wayland is asked for: the context is created through SDL2 and EGL.
function check_gles() {
    local cc="${CC:-cc}"
    local -a cflags=()
    pkg-config --exists glesv2 egl \
        || die "pkg-config finds no OpenGL ES (glesv2) or EGL (egl) development files"
    read -r -a cflags < <(pkg-config --cflags glesv2 egl) || true
    printf '#include <EGL/egl.h>\n#include <GLES3/gl3.h>\nint main(void) { return 0; }\n' |
        "${cc}" -x c "${cflags[@]}" -fsyntax-only - &>/dev/null \
        || die "No OpenGL ES 3.0 headers (GLES3/gl3.h, EGL/egl.h): GLideN64 needs them"
    # not fatal, SDL2 may be replaced by the one of the target system: only the
    # headers of this machine are checked
    local -a sdl_cflags=()
    read -r -a sdl_cflags < <(pkg-config --cflags sdl2) || true
    printf '#include <SDL_config.h>\n#ifndef SDL_VIDEO_OPENGL_ES2\n#error no OpenGL ES in SDL2\n#endif\n' |
        "${cc}" -x c "${sdl_cflags[@]}" -fsyntax-only - &>/dev/null \
        || log_warn "This SDL2 was built without OpenGL ES: the plugins will not get a context."
}


# gles_make_vars: the variables that make the Makefile of the core, of Glide64mk2
# and of Rice build against OpenGL ES instead of desktop OpenGL, one per line.
# USE_GLES=1 defines USE_GLES (which also picks Glide64mk2's OGLES sources) and
# links GLESv2; batocera also links EGL, and the flags come from pkg-config.
function gles_make_vars() {
    echo "USE_GLES=1"
    echo "GL_CFLAGS=$(pkg-config --cflags glesv2 egl)"
    echo "GL_LDLIBS=$(pkg-config --libs glesv2 egl)"
}


# build_gliden64 <flags>: GLideN64 builds with cmake, not with a Makefile.
function build_gliden64() {
    local flags="$1" folder="${SRC_DIR}/gliden64" plugin version
    local -a generator=() options=()
    if command -v ninja &>/dev/null; then
        generator=(-G Ninja)
    fi
    if is_arm64; then
        options+=(-DCRC_ARMV8=ON)
    fi
    if [[ "${GL_API}" == "gles" ]]; then
        # EGL: OpenGL ES, and no desktop OpenGL lookup (find_package(OpenGL) is only
        # done without it); MESA: no Raspberry Pi autodetection (/opt/vc), whose
        # Broadcom libraries are not the ones to link against on a Mesa system.
        # The plugin takes its context from the core through SDL2: it links neither
        # X11 nor Wayland, so the same plugin runs under any of them or under KMS/DRM
        options+=(-DEGL=ON -DMESA=ON)
    fi
    fetch_part gliden64 "${folder}"
    log_info "Building ${LABEL}'s GLideN64 plugin with ${JOBS} jobs..."
    cmake -S "${folder}/src" -B "${folder}/build" "${generator[@]}" \
        -DCMAKE_BUILD_TYPE=Release -DMUPENPLUSAPI=ON -DMUPENPLUSAPI_GLIDENUI=OFF \
        -DUSE_SYSTEM_LIBS=ON "${options[@]}" \
        -DCMAKE_C_FLAGS="${flags}" -DCMAKE_CXX_FLAGS="${flags} -include cstdint" \
        || die "CMake could not configure GLideN64: check the messages above"
    cmake --build "${folder}/build" -j "${JOBS}" \
        || die "The build of GLideN64 failed (lower JOBS if the linker ran out of memory)"
    plugin="$(find "${folder}" -name mupen64plus-video-GLideN64.so -print -quit)"
    [[ -n "${plugin}" ]] || die "The build did not produce mupen64plus-video-GLideN64.so"
    install -D "${plugin}" "${STAGE}/lib/mupen64plus/mupen64plus-video-gliden64.so"
    cp -a "${folder}/ini/." "${STAGE}/share/mupen64plus/"
    # the plugin resets its section of mupen64plus.cfg when the version found there is
    # not its own, and with it every option configgen wrote: configgen reads this one
    version="$(sed -n 's/^#define CONFIG_VERSION_CURRENT[[:space:]]*\([0-9]*\).*/\1/p' \
        "${folder}/src/Config.h")"
    if [[ -n "${version}" ]]; then
        echo "${version}" >"${STAGE}/share/mupen64plus/gliden64_config_version"
    else
        log_warn "Could not read the settings version of GLideN64: its options may be reset."
    fi
}


# install_fonts: the font of the on-screen messages, from the system's DejaVu Sans.
function install_fonts() {
    local font
    font="$(find /usr/share/fonts -name DejaVuSans.ttf -print -quit 2>/dev/null || true)"
    if [[ -n "${font}" ]]; then
        ln -sf "${font}" "${STAGE}/share/mupen64plus/font.ttf"
    else
        log_warn "DejaVuSans.ttf is not installed: Mupen64Plus will show no messages."
    fi
}


function install_source() {
    case "${GL_API}" in
        gl | gles) ;;
        *) die "MUPEN64PLUS_GL must be gl or gles, not '${GL_API}'" ;;
    esac
    # What the graphics need. Desktop OpenGL: libGL, GLU and the X11 headers the
    # Makefiles of the plugins look for. OpenGL ES: only the headers and libraries
    # of OpenGL ES and EGL (libglvnd's), with no X11, no Wayland and no GLU.
    local apt_gl="" dnf_gl=""
    if [[ "${GL_API}" == "gles" ]]; then
        apt_gl="libgles-dev|libgles2-mesa-dev libegl-dev|libegl1-mesa-dev"
        dnf_gl="libglvnd-devel"
    else
        apt_gl="libgl-dev|libgl1-mesa-dev libglu1-mesa-dev libx11-dev"
        dnf_gl="mesa-libGL-devel mesa-libGLU-devel libX11-devel"
    fi
    # nasm only assembles the x86 sources
    local apt_nasm="" dnf_nasm=""
    if [[ "${ARCH}" == "x86_64" ]]; then
        apt_nasm="nasm"
        dnf_nasm="nasm"
    fi
    install_packages \
        "build-essential cmake ninja-build git curl pkg-config python3 ${apt_nasm}
         libsdl2-dev libasound2-dev libfreetype-dev|libfreetype6-dev libpng-dev
         zlib1g-dev libboost-dev fonts-dejavu-core ${apt_gl}" \
        "gcc-c++ make cmake ninja-build git curl pkgconf-pkg-config python3 ${dnf_nasm}
         SDL2-devel alsa-lib-devel freetype-devel libpng-devel zlib-devel
         boost-devel dejavu-sans-fonts ${dnf_gl}"
    local flags="${MUPEN64PLUS_CFLAGS:--O3 -march=native -pipe}" part
    # batocera builds the core with these: its C does not pass on newer compilers as it is
    local core_flags="${flags} -std=gnu17 -D_GNU_SOURCE"
    core_flags+=" -Wno-error=implicit-function-declaration -Wno-error=int-conversion"
    core_flags+=" -Wno-error=incompatible-pointer-types"
    # the new dynamic recompiler: the Makefile picks it on ARM by itself, on x86_64
    # it has to be asked for (the old one loops on some games)
    local -a core_vars=() gl_vars=()
    if [[ "${ARCH}" == "x86_64" ]] || is_arm64; then
        core_vars+=(NEW_DYNAREC=1)
    fi
    if [[ "${GL_API}" == "gles" ]]; then
        check_gles
        mapfile -t gl_vars < <(gles_make_vars)
        log_info "Building against OpenGL ES (MUPEN64PLUS_GL=gles), with no X11 or Wayland: Glide64mk2 ignores RenderHeight, overscan and WaitForGPU."
    fi
    rm -rf "${SRC_DIR}"
    mkdir -p "${SRC_DIR}"
    for part in "${MAKE_PARTS[@]}"; do
        fetch_part "${part}" "${SRC_DIR}/${part}"
        case "${part}" in
            core) make_part "${part}" "${core_flags}" "${core_vars[@]}" "${gl_vars[@]}" ;;
            video_glide64mk2 | video_rice) make_part "${part}" "${flags}" "${gl_vars[@]}" ;;
            *) make_part "${part}" "${flags}" ;;
        esac
    done
    build_gliden64 "${flags}"
    install_fonts
    # which API the plugins were built for, for what has to differ between the two
    echo "${GL_API}" >"${STAGE}/share/mupen64plus/gl_api"
    require_executable bin/mupen64plus
    for part in audio-sdl input-sdl rsp-hle video-glide64mk2 video-rice video-gliden64; do
        [[ -f "${STAGE}/lib/mupen64plus/mupen64plus-${part}.so" ]] \
            || die "The install did not produce mupen64plus-${part}.so"
    done
    [[ -f "${STAGE}/lib/libmupen64plus.so.2.0.0" ]] \
        || die "The install did not produce libmupen64plus.so.2.0.0"
    remove_sources
}


installer_main "$@"
