#!/usr/bin/env bash
# Kodi, for the apps system and EmulationStation's Kodi menu entry: the
# Flathub Flatpak (tv.kodi.Kodi) on x86_64 when flatpak is installed, else a
# build from source (always on aarch64). Either way it comes with the
# WebApp Launcher add-on (plugin.program.webapplauncher), put in that Kodi's
# add-ons folder and enabled by configgen before Kodi starts.
#
# The build is the latest stable release of Kodi (KODI_REF picks another tag
# or branch), with the peripheral.joystick add-on that Retrobox's controller
# maps need. KODI_PLATFORM (x11) and KODI_RENDER (gl on x86_64, gles on ARM)
# are passed to its CMAKE (CORE_PLATFORM_NAME, APP_RENDER_SYSTEM).
#
#   kodi.sh --joystick-addon   build only peripheral.joystick for the Kodi
#                              already installed (one built before Retrobox
#                              added the add-on, or whose add-on is gone): it
#                              builds from the sources of that Kodi's release
#                              in minutes, not hours; the build tools are
#                              those of the source install above
EMULATOR="kodi"
LABEL="Kodi"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly FLATPAK_ID="tv.kodi.Kodi"
# in the install: the Kodi release it was built from
readonly REF_FILE=".retrobox-kodi-ref"
readonly ADDON_ID="plugin.program.webapplauncher"
readonly ADDON_REPO="https://github.com/manu-romero-411/plugin.program.webapplauncher.git"

function install_flatpak() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "Kodi is built from source on ${ARCH}."
    flatpak_install "${FLATPAK_ID}"
}

# The newest stable release tag of Kodi (21.2-Omega...): no alphas, betas or
# release candidates.
function latest_kodi_tag() {
    git ls-remote --tags --refs https://github.com/xbmc/xbmc.git 2>/dev/null | python3 -I -c '
import re, sys
best = None
for line in sys.stdin:
    tag = line.rsplit("/", 1)[-1].strip()
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?-([A-Za-z]+)", tag)
    if match:
        key = tuple(int(part or 0) for part in match.groups()[:3])
        if best is None or key > best[0]:
            best = (key, tag)
if best is None:
    sys.exit(1)
print(best[1])'
}

# Whether the distribution's SWIG is older than 4.5, which newer Kodi needs.
function swig_too_old() {
    local version
    version="$(swig -version 2>/dev/null | sed -n 's/^SWIG Version \([0-9.]*\).*/\1/p')"
    [[ -z "${version}" ]] && return 0
    [[ "$(printf '%s\n4.5.0\n' "${version}" | sort -V | head -n 1)" != "4.5.0" ]]
}

function install_source() {
    install_packages \
        "build-essential autoconf automake autopoint autotools-dev cmake ninja-build git curl
         default-jre-headless gawk gettext gperf pkg-config bison libtool meson nasm swig unzip zip
         libasound2-dev libass-dev libavahi-client-dev libavahi-common-dev libbluray-dev
         libbz2-dev libcdio-dev libcec-dev libcrossguid-dev libcurl4-openssl-dev libdbus-1-dev
         libdrm-dev libegl1-mesa-dev|libegl-dev libenca-dev libexiv2-dev libflac-dev
         libflatbuffers-dev libfmt-dev libfontconfig-dev libfreetype-dev|libfreetype6-dev
         libfribidi-dev libfstrcmp-dev libgcrypt20-dev libgif-dev libgl1-mesa-dev|libgl-dev
         libgles2-mesa-dev|libgles-dev libglu1-mesa-dev libgnutls28-dev libgpg-error-dev
         libgtest-dev libiso9660-dev libjpeg-dev liblcms2-dev liblirc-dev libltdl-dev
         liblzo2-dev libmicrohttpd-dev default-libmysqlclient-dev|libmysqlclient-dev libnfs-dev
         libogg-dev libpcre2-dev libplist-dev libpng-dev libpulse-dev libsmbclient-dev
         libspdlog-dev libsqlite3-dev libssl-dev libtag1-dev|libtag-dev libtiff-dev
         libtinyxml-dev libtinyxml2-dev libudev-dev libunistring-dev libva-dev libvdpau-dev
         libvorbis-dev libxkbcommon-dev libxmu-dev libxrandr-dev libxt-dev lsb-release
         nlohmann-json3-dev rapidjson-dev python3-dev python3-pil uuid-dev zlib1g-dev" \
        "gcc gcc-c++ make autoconf automake cmake ninja-build git curl java-latest-openjdk-headless
         gawk gettext gettext-devel gperf pkgconf-pkg-config bison libtool meson nasm swig unzip
         zip alsa-lib-devel libass-devel avahi-devel libbluray-devel bzip2-devel libcdio-devel
         libcec-devel crossguid2-devel libcurl-devel dbus-devel libdrm-devel mesa-libEGL-devel
         enca-devel exiv2-devel flac-devel flatbuffers-devel flatbuffers-compiler fmt-devel
         fontconfig-devel freetype-devel fribidi-devel fstrcmp-devel libgcrypt-devel
         giflib-devel mesa-libGL-devel mesa-libGLES-devel mesa-libGLU-devel gnutls-devel
         gtest-devel lcms2-devel lirc-devel libtool-ltdl-devel lzo-devel libmicrohttpd-devel
         mariadb-devel libnfs-devel libogg-devel pcre2-devel libplist-devel libpng-devel
         pulseaudio-libs-devel libsmbclient-devel spdlog-devel sqlite-devel openssl-devel
         taglib-devel libtiff-devel tinyxml-devel tinyxml2-devel systemd-devel libunistring-devel
         libva-devel libvdpau-devel libvorbis-devel libxkbcommon-devel libXmu-devel
         libXrandr-devel libXt-devel json-devel rapidjson-devel python3-devel python3-pillow
         libuuid-devel zlib-devel"
    local ref="${KODI_REF:-}" render="${KODI_RENDER:-}"
    if [[ -z "${ref}" ]]; then
        ref="$(latest_kodi_tag)" || die "Could not find Kodi's latest release (network down?)"
    fi
    if [[ -z "${render}" ]]; then
        render="gl"
        [[ "${ARCH}" == "x86_64" ]] || render="gles"
    fi
    local -a extra=()
    # SWIG 4.5 or newer for the Python bindings of newer Kodi: else its own copy
    swig_too_old && extra+=(-DENABLE_INTERNAL_SWIG=ON)
    # Kodi up to 21 needs PCRE1, gone from Debian 13 and recent Fedora: build
    # its own static copy (newer Kodi uses PCRE2 and ignores the option)
    pkg-config --exists libpcre 2>/dev/null || extra+=(-DENABLE_INTERNAL_PCRE=ON)
    git_clone https://github.com/xbmc/xbmc.git "${ref}"
    cmake_build -DCORE_PLATFORM_NAME="${KODI_PLATFORM:-x11}" -DAPP_RENDER_SYSTEM="${render}" \
        -DENABLE_INTERNAL_FFMPEG=ON -DENABLE_INTERNAL_CROSSGUID=ON -DENABLE_TESTING=OFF \
        "${extra[@]}"
    cmake_install
    require_executable bin/kodi

    # the release the add-on of --joystick-addon has to be built from
    printf '%s\n' "${ref}" >"${STAGE}/${REF_FILE}"
    # an add-on that fails does not throw away the hours of Kodi's build: Kodi
    # is installed, and --joystick-addon builds the add-on again in minutes
    if ! (build_joystick_addon "${ref}" "${STAGE}"); then
        log_warn "Kodi is installed without peripheral.joystick (controllers will not work in it):"
        log_warn "build it with '$0 --joystick-addon' once the problem above is solved."
    fi
    remove_sources
}

# The branch of Kodi's binary add-ons that goes with a Kodi ref: the codename of
# a release tag (21.3-Omega: Omega), else master.
function addons_branch() {
    local ref="$1"
    if [[ "${ref}" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?-([A-Za-z]+)$ ]]; then
        echo "${BASH_REMATCH[2]}"
    else
        echo "master"
    fi
}

# build_joystick_addon <kodi ref> <prefix>: peripheral.joystick, through which
# Kodi reads the controllers (and Retrobox's button maps), built against the
# Kodi source tree in ${SRC_DIR} (which needs no build of its own) and
# installed under <prefix> (lib/kodi/addons and share/kodi/addons).
#
# Kodi's add-on superbuild (cmake/addons) is only configured, for the CMake
# files the add-on builds against: built, it downloads the add-on and its
# dependencies as tarballs, and when a download fails it says nothing and
# installs nothing. So the add-on is cloned with git and built on its own,
# with the distribution's tinyxml and libudev.
function build_joystick_addon() {
    local ref="$1" prefix="$2" branch sources="${SRC_DIR}/addon-sources"
    local env="${SRC_DIR}/build-addons" build="${SRC_DIR}/build-joystick"
    branch="$(addons_branch "${ref}")"
    log_info "Building Kodi's peripheral.joystick add-on (${branch})..."
    rm -rf "${sources}" "${env}" "${build}"
    git clone --depth 1 --branch "${branch}" https://github.com/xbmc/peripheral.joystick.git \
        "${sources}/peripheral.joystick" || die "Could not clone peripheral.joystick (${branch})"
    cmake -S "${SRC_DIR}/cmake/addons" -B "${env}" -DADDONS_TO_BUILD=peripheral.joystick \
        -DADDON_SRC_PREFIX="${sources}" -DCORE_SOURCE_DIR="${SRC_DIR}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="${env}/unused" -DPACKAGE_ZIP=OFF \
        || die "CMake could not prepare Kodi's add-on environment"
    [[ -f "${env}/build/depends/lib/kodi/KodiConfig.cmake" ]] \
        || die "Kodi's add-on environment has no KodiConfig.cmake"
    cmake -S "${sources}/peripheral.joystick" -B "${build}" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_PREFIX_PATH="${env}/build/depends" -DOVERRIDE_PATHS=ON \
        -DCMAKE_INSTALL_PREFIX="${prefix}" || die "CMake could not configure peripheral.joystick"
    cmake --build "${build}" -j "${JOBS}" || die "The peripheral.joystick add-on did not build"
    cmake --install "${build}" || die "The peripheral.joystick add-on did not install"
    if [[ ! -f "${prefix}/share/kodi/addons/peripheral.joystick/addon.xml" ]] ||
        ! compgen -G "${prefix}/lib/kodi/addons/peripheral.joystick/peripheral.joystick.so*" >/dev/null; then
        die "The build did not produce the peripheral.joystick add-on"
    fi
}

# The Kodi release to build the add-on from: KODI_REF, else the one the install
# recorded, else the one `kodi --version` reports, else the latest.
function installed_kodi_ref() {
    local version tag
    if [[ -n "${KODI_REF:-}" ]]; then
        echo "${KODI_REF}"
    elif [[ -s "${APP_DIR}/${REF_FILE}" ]]; then
        head -n 1 "${APP_DIR}/${REF_FILE}"
    else
        version="$(timeout 30 "${APP_DIR}/bin/kodi" --version 2>/dev/null \
            | grep -oE '[0-9]+\.[0-9]+' | head -n 1 || true)"
        tag=""
        if [[ -n "${version}" ]]; then
            tag="$(git ls-remote --tags --refs https://github.com/xbmc/xbmc.git 2>/dev/null \
                | sed 's|.*/||' | grep -E "^${version//./\\.}(\.[0-9]+)?-[A-Za-z]+$" \
                | sort -V | tail -n 1 || true)"
        fi
        if [[ -z "${tag}" ]]; then
            log_warn "Could not tell which release of Kodi is installed: using the latest."
            tag="$(latest_kodi_tag)" || die "Could not find Kodi's latest release (network down?)"
        fi
        echo "${tag}"
    fi
}

# --joystick-addon: the add-on for the Kodi that is installed, in place.
function repair_joystick_addon() {
    [[ -x "${APP_DIR}/bin/kodi" ]] \
        || die "No Kodi built by Retrobox in ${APP_DIR}: install it first."
    [[ ! -f "${APP_DIR}/${FLATPAK_MARKER}" ]] \
        || die "The Flatpak Kodi comes with its own peripheral.joystick."
    install_packages "git cmake build-essential pkg-config libtinyxml-dev libudev-dev" \
        "git cmake gcc-c++ make pkgconf-pkg-config tinyxml-devel systemd-devel"
    local ref
    ref="$(installed_kodi_ref)"
    # a failure removes the sources (the exit trap does it while staging)
    _STAGING=1
    log_info "Building the add-on from Kodi ${ref}..."
    rm -rf "${SRC_DIR}"
    mkdir -p "$(dirname "${SRC_DIR}")"
    git clone --depth 1 --branch "${ref}" https://github.com/xbmc/xbmc.git "${SRC_DIR}" \
        || die "Could not clone Kodi ${ref}"
    build_joystick_addon "${ref}" "${APP_DIR}"
    printf '%s\n' "${ref}" >"${APP_DIR}/${REF_FILE}"
    remove_sources
    _STAGING=0
    log_ok "peripheral.joystick is in ${APP_DIR}: start Kodi again."
}

# Where the Kodi just installed keeps its add-ons.
function addons_dir() {
    if [[ -f "${APP_DIR}/${FLATPAK_MARKER}" ]]; then
        echo "${HOME}/.var/app/${FLATPAK_ID}/data/addons"
    else
        echo "${HOME}/.kodi/addons"
    fi
}

# The WebApp Launcher add-on, in the add-ons of that Kodi: the newest of its
# repository, replacing an older copy (its settings, in userdata, stay).
function after_install() {
    local work target
    work="$(mktemp -d -p "${TMP_DIR}")"
    log_info "Downloading the WebApp Launcher add-on (${ADDON_ID})..."
    need git
    git clone --depth 1 "${ADDON_REPO}" "${work}/${ADDON_ID}" \
        || die "Could not download ${ADDON_REPO}"
    [[ -f "${work}/${ADDON_ID}/addon.xml" ]] || die "${ADDON_REPO} has no addon.xml"
    rm -rf "${work:?}/${ADDON_ID}/.git" "${work}/${ADDON_ID}/.gitignore"
    target="$(addons_dir)"
    mkdir -p "${target}"
    rm -rf "${target:?}/${ADDON_ID}"
    mv "${work}/${ADDON_ID}" "${target}/${ADDON_ID}"
    log_ok "The WebApp Launcher add-on is in ${target}/${ADDON_ID}."
}

if [[ "${1:-}" == "--joystick-addon" ]]; then
    repair_joystick_addon
else
    installer_main "$@"
fi
