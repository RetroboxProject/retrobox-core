#!/usr/bin/env bash
# tools/utils/mangohud.sh — build & install MangoHud from source, following
# the exact version/patch set Batocera ships for it, installed under
# /usr/local. On x86_64 this builds dual 32+64 bit OpenGL/Vulkan support,
# same as Batocera; on any other host (aarch64 and friends) there's no
# 32-bit companion build, so it's 64-bit only. The 32-bit pass on x86_64
# can also be skipped explicitly with -n (see usage below).
#
# Invoked by tools/setup.sh's setup_util() as:
#   bash tools/utils/mangohud.sh -s        (source build — the only option
#                                            this installer has)
#   bash tools/utils/mangohud.sh -s -n     (source build, 64-bit only, even
#                                            on x86_64)
#   bash tools/utils/mangohud.sh -u        (uninstall)
#
# i.e. via `retrobox --setup-util mangohud`.
#
# What -s does:
#   1. Detects and removes any existing MangoHud install (dnf, apt, or a
#      previous from-source install done by this same script).
#   2. Downloads package/batocera/utils/mangohud/mangohud.mk from the
#      batocera.linux repo to read which tag Batocera builds, and downloads
#      every patch in that same folder.
#   3. Clones MangoHud at that tag (with submodules) and applies the patches.
#   4. Builds it for the native architecture, plus a second 32-bit pass via
#      gcc -m32 when the host is x86_64 (unless -n was given), with
#      --prefix /usr/local, mirroring Batocera's meson options.
#   5. Installs the tree(s) under /usr/local/lib/mangohud/{lib64,lib32},
#      fixes the `mangohud` wrapper and recreates the $LIB/$PLATFORM
#      compatibility symlinks used by the project's own upstream build.sh
#      (only the x86_64 32-bit-companion ones are architecture-specific;
#      other 64-bit-only hosts — real ones, or x86_64 run with -n — get a
#      smaller, generic set — see fix_wrapper_and_symlinks below).
#
#      NOTE on $LIB: MangoHud's bin/mangohud.in wrapper template, by
#      default, doesn't bake a resolved lib path — it hardcodes the
#      literal string "$LIB" into LD_PRELOAD/LD_LIBRARY_PATH and relies on
#      ld.so's own dynamic string token substitution to turn it into
#      "lib64"/"lib32" at exec time. That substitution does not reliably
#      happen for every launcher (e.g. apps launched through a
#      bundled/portable interpreter such as sharun, which needs
#      SHARUN_ALLOW_LD_PRELOAD=1 just to attempt preloading at all, and
#      known to mishandle $LIB regardless of host arch — see
#      flightlessmango/MangoHud#665 for the same failure on plain aarch64
#      too). Since retrobox only ever wraps 64-bit emulator binaries,
#      $LIB's runtime bitness-selection is never actually needed here, so
#      the build passes -Ddynamic_string_tokens=false (meson_opts_common)
#      to make Meson bake the real absolute libdir straight into the
#      wrapper at build time instead — this fixes OpenGL/LD_PRELOAD
#      hooking (e.g. Dolphin) unconditionally, on any host arch, with no
#      post-install patching needed. Vulkan was never affected by this,
#      since its implicit-layer JSON is already generated from the
#      absolute libdir too (src/meson.build's ld_libdir_mangohud_abs),
#      never from the "$LIB" token.
set -euo pipefail

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
SCRIPT_DIR="${RETROBOX_ROOT}/tools/utils"

# shellcheck source=../lib/log.sh
source "${SCRIPT_DIR}/../lib/log.sh"

MANGOHUD_GIT_URL="https://github.com/flightlessmango/MangoHud.git"
BATOCERA_PKG_DIR="package/batocera/utils/mangohud"
BATOCERA_MK_RAW_URL="https://raw.githubusercontent.com/batocera-linux/batocera.linux/master/${BATOCERA_PKG_DIR}/mangohud.mk"
BATOCERA_API_DIR_URL="https://api.github.com/repos/batocera-linux/batocera.linux/contents/${BATOCERA_PKG_DIR}"

PREFIX="${RETROBOX_ROOT}/libexec/mangohud"
PACKAGE_STATE_DIR="${RETROBOX_ROOT}/tools/.packages/utils/mangohud"

# MangoHud is installed inside the Retrobox install tree (where the
# retrobox-mangohud package puts it), so this needs write access to it.
if [[ ! -w "${RETROBOX_ROOT}/libexec" || ! -w "${RETROBOX_ROOT}/tools" ]]; then
    echo "[ERR ] ${RETROBOX_ROOT} is not writable by this user. Run: sudo retrobox --setup-util mangohud" >&2
    exit 1
fi
MANIFEST_FILE="${PACKAGE_STATE_DIR}/mangohud.manifest"
VERSION_FILE="${PACKAGE_STATE_DIR}/mangohud.version"

WORKDIR="${TMPDIR:-/tmp}/retrobox-mangohud-build"
SRC_DIR="${WORKDIR}/MangoHud"
PATCH_DIR="${WORKDIR}/patches"
STAGE_DIR="${WORKDIR}/stage"

# Retrobox's own patches (background_image/image, etc.), maintained manually 
# in the repo -- not downloaded from anywhere. They are generated with 
# `git format-patch` against a clean MangoHud tag and applied AFTER 
# Batocera's patches (see apply_patches_from_dir in fetch_and_patch_source).
LOCAL_PATCH_DIR="${SCRIPT_DIR}/mangohud-patches"

MACHINE="$(uname -m)"

# Set by argument parsing at the bottom of the script. When 1, the 32-bit
# (i386) build pass is skipped even on an x86_64 host. Default is 0 (build it).
SKIP_32BIT=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# True (0) when a 32-bit companion build should actually happen: only on
# x86_64 hosts, and only when the caller hasn't opted out with -n.
want_32bit() {
    [[ "${MACHINE}" == "x86_64" && "${SKIP_32BIT}" -eq 0 ]]
}

detect_pkg_manager() {
    if command -v dnf >/dev/null 2>&1; then
        echo dnf
    elif command -v apt-get >/dev/null 2>&1; then
        echo apt
    else
        echo unknown
    fi
}
PKG_MGR="$(detect_pkg_manager)"

as_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

# ---------------------------------------------------------------------------
# Remove any previous MangoHud installation
# ---------------------------------------------------------------------------

uninstall_from_source_manifest() {
    [[ -f "${MANIFEST_FILE}" ]] || { log_info "No install manifest to undo."; return 0; }
    log_info "Removing files listed in ${MANIFEST_FILE}..."
    tac "${MANIFEST_FILE}" | while IFS= read -r path; do
        [[ -e "${path}" || -L "${path}" ]] || continue
        as_root rm -f "${path}" 2>/dev/null || as_root rmdir "${path}" 2>/dev/null || true
    done
    # The manifest belongs to the user, no as_root needed for deletion
    rm -f "${MANIFEST_FILE}" "${VERSION_FILE}"
}

remove_existing_install() {
    local found=0
    local user_vulkan_dir="${HOME}/.local/share/vulkan/implicit_layer.d"
    local prefix_vulkan_dir="${PREFIX}/share/vulkan/implicit_layer.d"

    if command -v rpm >/dev/null 2>&1 && rpm -q mangohud &>/dev/null 2>&1; then
        found=1
        log_warn "MangoHud installed via dnf/rpm — removing it."
        as_root dnf remove -y mangohud
    fi

    if command -v dpkg >/dev/null 2>&1 && dpkg -s mangohud &>/dev/null 2>&1; then
        found=1
        log_warn "MangoHud installed via apt/dpkg — removing it."
        as_root apt-get remove -y mangohud
    fi

    if [[ -f "${MANIFEST_FILE}" ]]; then
        found=1
        log_warn "A previous from-source install was detected — cleaning it up before rebuilding."
        uninstall_from_source_manifest
    fi

    # Clean up system legacy files
    local system_legacy_files=(
        "/usr/lib/mangohud"
        "/usr/bin/mangohud"
        "/usr/bin/mangoplot"
        "/usr/share/vulkan/implicit_layer.d/RetroboxMangoHud.x86_64.json"
        "/usr/share/vulkan/implicit_layer.d/RetroboxMangoHud.x86.json"
        "/usr/share/vulkan/implicit_layer.d/RetroboxMangoHud.json"
        "/usr/share/vulkan/implicit_layer.d/retroboxmangohud.json"
        "/usr/local/share/vulkan/implicit_layer.d/RetroboxMangoHud.x86_64.json"
        "/usr/local/share/vulkan/implicit_layer.d/RetroboxMangoHud.x86.json"
        "/usr/local/share/vulkan/implicit_layer.d/RetroboxMangoHud.json"
        "/usr/local/share/vulkan/implicit_layer.d/retroboxmangohud.json"
    )
    for legacy in "${system_legacy_files[@]}"; do
        if [[ -e "${legacy}" || -L "${legacy}" ]]; then
            found=1
            log_warn "Leftover from a manual install under /usr or /usr/local: ${legacy}"
            as_root rm -rf "${legacy}"
        fi
    done

    # Clean up user and prefix directory legacy files
    local user_legacy_files=(
        "${user_vulkan_dir}/RetroboxMangoHud.x86_64.json"
        "${user_vulkan_dir}/RetroboxMangoHud.x86.json"
        "${user_vulkan_dir}/RetroboxMangoHud.json"
        "${user_vulkan_dir}/retroboxmangohud.json"
        "${prefix_vulkan_dir}/RetroboxMangoHud.x86_64.json"
        "${prefix_vulkan_dir}/RetroboxMangoHud.x86.json"
        "${prefix_vulkan_dir}/RetroboxMangoHud.json"
        "${prefix_vulkan_dir}/retroboxmangohud.json"
    )
    for legacy in "${user_legacy_files[@]}"; do
        if [[ -e "${legacy}" || -L "${legacy}" ]]; then
            found=1
            log_warn "Leftover from a manual install: ${legacy}"
            rm -f "${legacy}"
        fi
    done

    [[ "${found}" -eq 0 ]] && log_info "No previous MangoHud installation found."
}

# ---------------------------------------------------------------------------
# Batocera's recipe: version + patches
# ---------------------------------------------------------------------------

fetch_batocera_recipe() {
    mkdir -p "${PATCH_DIR}"

    log_info "Downloading mangohud.mk from batocera.linux..."
    curl -fsSL "${BATOCERA_MK_RAW_URL}" -o "${WORKDIR}/mangohud.mk"

    BATOCERA_VERSION="$(sed -n 's/^MANGOHUD_VERSION\s*=\s*//p' "${WORKDIR}/mangohud.mk" | tr -d '[:space:]')"
    if [[ -z "${BATOCERA_VERSION}" ]]; then
        log_err "Could not extract MANGOHUD_VERSION from mangohud.mk"
        exit 1
    fi
    log_info "Version used by Batocera: ${BATOCERA_VERSION}"

    log_info "Listing patches in ${BATOCERA_PKG_DIR}..."
    local listing="${WORKDIR}/dir-listing.json"
    curl -fsSL -H "Accept: application/vnd.github+json" "${BATOCERA_API_DIR_URL}" -o "${listing}"

    # Batocera's patches follow the NNN-description(.patch|.json) pattern;
    # the odd .json in there (001-no-mangohud.json) is actually a diff too,
    # so we pick files by their numeric prefix, not by extension.
    python3 - "${listing}" "${PATCH_DIR}" <<'PYEOF'
import json, sys, re, urllib.request, os

listing_path, patch_dir = sys.argv[1], sys.argv[2]
with open(listing_path) as f:
    entries = json.load(f)

pat = re.compile(r'^\d{3}-.*')
picked = sorted(
    (e for e in entries if e.get("type") == "file" and pat.match(e.get("name", ""))),
    key=lambda e: e["name"],
)
if not picked:
    print("No patches matching the NNN-* pattern were found.", file=sys.stderr)

for e in picked:
    dest = os.path.join(patch_dir, e["name"])
    urllib.request.urlretrieve(e["download_url"], dest)
    print(f"  - {e['name']}")
PYEOF
}

# Applies, in order, all files from a patch directory to ${SRC_DIR}. 
# Used for both official Batocera patches (downloaded at runtime to ${PATCH_DIR}) 
# and Retrobox's own patches (versioned in ${LOCAL_PATCH_DIR}).
apply_patches_from_dir() {
    local dir="$1" label="$2"
    shopt -s nullglob
    local patches=("${dir}"/*)
    shopt -u nullglob
    if [[ "${#patches[@]}" -eq 0 ]]; then
        log_warn "No ${label} patches to apply."
        return 0
    fi
    for p in "${patches[@]}"; do
        log_info "Applying patch (${label}): $(basename "${p}")"
        git apply --whitespace=nowarn -p1 "${p}" 2>/dev/null \
            || git apply --whitespace=nowarn -p1 --3way "${p}" 2>/dev/null \
            || patch -p1 --forward --fuzz=3 < "${p}" \
            || log_warn "Patch $(basename "${p}") (${label}) could not be applied -- review it manually against the current MangoHud."
    done
}

fetch_and_patch_source() {
    rm -rf "${SRC_DIR}"

    if [[ "${BATOCERA_VERSION}" =~ ^[0-9a-fA-F]{40}$ ]]; then
        log_info "Cloning MangoHud at commit ${BATOCERA_VERSION}..."
        mkdir -p "${SRC_DIR}"
        git -C "${SRC_DIR}" init --quiet
        git -C "${SRC_DIR}" remote add origin "${MANGOHUD_GIT_URL}"
        git -C "${SRC_DIR}" fetch --quiet --depth 1 origin "${BATOCERA_VERSION}"
        git -C "${SRC_DIR}" checkout --quiet FETCH_HEAD
        git -C "${SRC_DIR}" submodule update --init --recursive --depth 1
    else
        log_info "Cloning MangoHud (${BATOCERA_VERSION})..."
        git clone --quiet --recurse-submodules --depth 1 \
            "${MANGOHUD_GIT_URL}" "${SRC_DIR}"
    fi

    cd "${SRC_DIR}"
    apply_patches_from_dir "${PATCH_DIR}" "batocera"
    apply_patches_from_dir "${LOCAL_PATCH_DIR}" "retrobox"
    cd - >/dev/null
}

# ---------------------------------------------------------------------------
# Build dependencies (including 32-bit)
# ---------------------------------------------------------------------------

detect_apt_backports_suite() {
    apt-cache policy 2>/dev/null \
        | grep -oP '\ba=\K[A-Za-z0-9._-]+-backports' \
        | sort -u | head -n1 || true
}

install_build_deps() {
    log_info "Installing build dependencies (${PKG_MGR})..."
    case "${PKG_MGR}" in
        dnf)
            local deps=(meson ninja-build gcc gcc-c++ git python3-mako glslang
                        dbus-devel json-devel wayland-devel libxkbcommon-devel
                        libX11-devel libdrm-devel mesa-libGL-devel
                        vulkan-loader-devel vulkan-headers libcurl-devel)
            local -a all_deps=("${deps[@]}")

            if want_32bit; then
                local deps32=(glibc-devel.i686 libstdc++-devel.i686 libX11-devel.i686
                              wayland-devel.i686 libxkbcommon-devel.i686
                              mesa-libGL-devel.i686 vulkan-loader-devel.i686)
                all_deps+=("${deps32[@]}")
            fi

            as_root dnf install -y "${all_deps[@]}"
            ;;
        apt)
            local deps=(meson ninja-build git python3-mako glslang-tools
                        libdbus-1-dev nlohmann-json3-dev libwayland-dev
                        libxkbcommon-dev libx11-dev libdrm-dev libgl1-mesa-dev
                        libvulkan-dev libcurl4-openssl-dev
                        libyaml-cpp-dev libwayland-egl-backend-dev)
            local -a all_deps=("${deps[@]}")

            if want_32bit; then
                if ! dpkg --print-foreign-architectures | grep -q i386; then
                    log_info "Enabling the i386 architecture for 32-bit libs..."
                    as_root dpkg --add-architecture i386
                    as_root apt-get update
                fi
                local deps32=(gcc-multilib g++-multilib libx11-dev:i386
                              libwayland-dev:i386 libxkbcommon-dev:i386
                              libgl1-mesa-dev:i386 libvulkan-dev:i386)
                all_deps+=("${deps32[@]}")
            fi

            local -a apt_install_opts=(install -y)
            local backports_suite
            backports_suite="$(detect_apt_backports_suite)"
            if [[ -n "${backports_suite}" ]]; then
                log_info "Backports repository detected (${backports_suite}); it will be used for whatever needs it."
                apt_install_opts+=(-t "${backports_suite}")
            fi

            as_root apt-get "${apt_install_opts[@]}" "${all_deps[@]}"
            ;;
        *)
            log_warn "Unrecognized package manager; install meson, ninja, glslang, dbus/json/wayland/x11/drm/vulkan (dev) manually for your architecture (plus the 32-bit multilib variants too, if this is an x86_64 host and you didn't pass -n)."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Build (64 + 32 bit) and install into /usr/local
# ---------------------------------------------------------------------------

meson_opts_common() {
    local opts=(-Dappend_libdir_mangohud=false -Dwith_xnvctrl=disabled
                -Ddynamic_string_tokens=false)

    if grep -q "'with_mangohud_next'" "${SRC_DIR}/meson_options.txt" 2>/dev/null; then
        opts+=(-Dwith_mangohud_next=false)
    fi

    pkg-config --exists x11 2>/dev/null && opts+=(-Dwith_x11=enabled) || opts+=(-Dwith_x11=disabled)
    pkg-config --exists wayland-client 2>/dev/null && opts+=(-Dwith_wayland=enabled) || opts+=(-Dwith_wayland=disabled)
    printf '%s\n' "${opts[@]}"
}

build_arch() {
    local bits="$1" builddir="$2" libdir="$3"
    cd "${SRC_DIR}"

    local -a opts
    mapfile -t opts < <(meson_opts_common)

    if [[ "${bits}" == "32" ]]; then
        export CC="gcc -m32"
        export CXX="g++ -m32"
        export PKG_CONFIG_PATH="/usr/lib32/pkgconfig:/usr/lib/i386-linux-gnu/pkgconfig:/usr/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    else
        unset CC CXX
        export PKG_CONFIG_PATH="/usr/lib64/pkgconfig:/usr/lib/${MACHINE}-linux-gnu/pkgconfig:/usr/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    fi

    log_info "Configuring the ${bits}-bit build..."
    meson setup "${builddir}" --prefix "${PREFIX}" --libdir "${libdir}" \
        --buildtype=release "${opts[@]}"

    log_info "Compiling the ${bits}-bit build..."
    ninja -C "${builddir}"

    log_info "Installing (staged) the ${bits}-bit build..."
    DESTDIR="${STAGE_DIR}" ninja -C "${builddir}" install

    unset CC CXX PKG_CONFIG_PATH
    cd - >/dev/null
}

merge_stage_into_prefix() {
    log_info "Merging into ${PREFIX} (requires privileges)..."
    # The manifest belongs to the user, no as_root needed for the state directory
    mkdir -p "${PACKAGE_STATE_DIR}"
    as_root rsync -a "${STAGE_DIR}${PREFIX}/" "${PREFIX}/"

    (cd "${STAGE_DIR}${PREFIX}" && find . -type f -o -type l) \
        | sed "s|^\.|${PREFIX}|" | tee "${MANIFEST_FILE}" >/dev/null
    echo "${BATOCERA_VERSION}" | tee "${VERSION_FILE}" >/dev/null
}

fix_wrapper_and_symlinks() {
    local libbase="${PREFIX}/lib/mangohud"
    local system_json_dir="/usr/local/share/vulkan/implicit_layer.d"
    local user_json_dir="${HOME}/.local/share/vulkan/implicit_layer.d"
    local prefix_json_dir="${PREFIX}/share/vulkan/implicit_layer.d"

    log_info "Registering MangoHud's libdir with ldconfig..."
    
    echo "${libbase}/lib64" | as_root tee /etc/ld.so.conf.d/mangohud.conf >/dev/null
    if want_32bit; then
        echo "${libbase}/lib32" | as_root tee -a /etc/ld.so.conf.d/mangohud.conf >/dev/null
    fi
    as_root ldconfig

    # Register the Vulkan implicit layer in the user directory (standard)
    log_info "Registering MangoHud Vulkan implicit layer in user and prefix directories..."
    mkdir -p "${user_json_dir}"
    
    # Also register in the prefix directory so the Python launcher (which uses MANGOHUD_VULKAN_LAYER_DIR) 
    # can find and inject it via VK_ADD_LAYER_PATH.
    mkdir -p "${prefix_json_dir}"
    mkdir -p "${system_json_dir}"

    local lib_path_64="${libbase}/lib64/libMangoHud.so"
    local json_content_64
    json_content_64=$(cat <<EOF
{
    "file_format_version" : "1.0.0",
    "layer" : {
      "name": "VK_LAYER_RETROBOX_MANGOHUD_overlay_x86_64",
      "type": "GLOBAL",
      "api_version": "1.3.0",
      "library_path": "${lib_path_64}",
      "implementation_version": "1",
      "description": "Vulkan Hud Overlay",
      "functions": {
         "vkNegotiateLoaderLayerInterfaceVersion": "vkNegotiateLoaderLayerInterfaceVersion"
      },
      "enable_environment": {
        "RETROBOX_MANGOHUD": "1"
      },
      "disable_environment": {
        "RETROBOX_MANGOHUD_DISABLE": "1"
      }
    }
}
EOF
)

    echo "${json_content_64}" | as_root tee "${system_json_dir}/RetroboxMangoHud.x86_64.json" >/dev/null
    echo "${json_content_64}" > "${prefix_json_dir}/RetroboxMangoHud.x86_64.json"
    log_info "Created Vulkan layer JSON in system and prefix directories."

    if want_32bit; then
        local lib_path_32="${libbase}/lib32/libMangoHud.so"
        local json_content_32
        json_content_32=$(cat <<EOF
{
    "file_format_version" : "1.0.0",
    "layer" : {
      "name": "VK_LAYER_RETROBOX_MANGOHUD_overlay_x86",
      "type": "GLOBAL",
      "api_version": "1.3.0",
      "library_path": "${lib_path_32}",
      "implementation_version": "1",
      "description": "Vulkan Hud Overlay",
      "functions": {
         "vkNegotiateLoaderLayerInterfaceVersion": "vkNegotiateLoaderLayerInterfaceVersion"
      },
      "enable_environment": {
        "RETROBOX_MANGOHUD": "1"
      },
      "disable_environment": {
        "RETROBOX_MANGOHUD_DISABLE": "1"
      }
    }
}
EOF
)
        echo "${json_content_32}" | as_root tee "${system_json_dir}/RetroboxMangoHud.x86.json" >/dev/null
        echo "${json_content_32}" > "${prefix_json_dir}/RetroboxMangoHud.x86.json"
    fi
}

isolate_from_system_env(){
    mkdir -p "${HOME}/.config/environment.d"
    cat << EOF > "${HOME}/.config/environment.d/64-retrobox-mangohud.conf"
# avoid conflict between system's and retrobox's mangohud on vulkan apps
RETROBOX_MANGOHUD_DISABLE=1
RETROBOX_MANGOHUD=0
EOF
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

do_install() {
    remove_existing_install
    rm -rf "${WORKDIR}"
    mkdir -p "${WORKDIR}"

    fetch_batocera_recipe
    install_build_deps
    fetch_and_patch_source

    build_arch 64 "${SRC_DIR}/build/meson64" "lib/mangohud/lib64"

    if want_32bit; then
        build_arch 32 "${SRC_DIR}/build/meson32" "lib/mangohud/lib32"
    else
        log_info "Skipping the 32-bit (i386) build."
    fi

    merge_stage_into_prefix
    fix_wrapper_and_symlinks
    isolate_from_system_env

    log_ok "MangoHud ${BATOCERA_VERSION} installed into ${PREFIX}."
}

do_uninstall() {
    # remove_existing_install already handles manifest undoing and legacy file cleanup
    remove_existing_install
    
    # Clean up ldconfig configuration
    as_root rm -f /etc/ld.so.conf.d/mangohud.conf
    as_root ldconfig || true
    
    # Clean up environment config (no root needed for user's home directory)
    rm -f "${HOME}/.config/environment.d/64-retrobox-mangohud.conf"

    log_ok "MangoHud uninstalled."
}

usage() {
    echo "Usage: $(basename "${BASH_SOURCE[0]}") -s [-n] | -u"
    echo "  -s   build and install MangoHud from source (Batocera's recipe)"
    echo "  -n   (with -s) skip the 32-bit (i386) build, even on x86_64"
    echo "  -u   uninstall the install done by this script"
}

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

case "$1" in
    "-s")
        do_install
        ;;
    "-u")
        do_uninstall
        ;;
    *)
        usage
        exit 1
        ;;
esac