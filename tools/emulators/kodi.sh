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
EMULATOR="kodi"
LABEL="Kodi"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly FLATPAK_ID="tv.kodi.Kodi"
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
    git_clone https://github.com/xbmc/xbmc.git "${ref}"
    cmake_build -DCORE_PLATFORM_NAME="${KODI_PLATFORM:-x11}" -DAPP_RENDER_SYSTEM="${render}" \
        -DENABLE_INTERNAL_FFMPEG=ON -DENABLE_INTERNAL_CROSSGUID=ON -DENABLE_TESTING=OFF \
        "${extra[@]}"
    cmake_install
    require_executable bin/kodi

    # peripheral.joystick: Kodi reads the controllers (and Retrobox's button
    # maps) through it; it is a binary add-on, built against this source tree
    log_info "Building Kodi's peripheral.joystick add-on..."
    cmake -S "${SRC_DIR}/cmake/addons" -B "${SRC_DIR}/build-addons" \
        -DADDONS_TO_BUILD=peripheral.joystick -DCORE_SOURCE_DIR="${SRC_DIR}" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="${STAGE}" -DPACKAGE_ZIP=OFF \
        || die "CMake could not configure Kodi's add-ons"
    cmake --build "${SRC_DIR}/build-addons" -j "${JOBS}" \
        || die "The peripheral.joystick add-on did not build"
    [[ -d "${STAGE}/share/kodi/addons/peripheral.joystick" ]] \
        || die "The build did not produce the peripheral.joystick add-on"
    remove_sources
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

installer_main "$@"
