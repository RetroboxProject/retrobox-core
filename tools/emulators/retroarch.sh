#!/usr/bin/env bash
# RetroArch: the nightly AppImage of the libretro buildbot (x86_64), or a
# build from source. Both install the frontend under app/ (bin/retroarch,
# share/retroarch/{assets,autoconfig,...}).
#
# The cores live next to app/, in cores/ (and their .info files in info/), so
# installing RetroArch again keeps them. The first install downloads the base
# cores (retrobox.cores.BASE_CORES); the rest are downloaded one by one, from
# EmulationStation's Content Downloader (the libretro tab) or with
# `retrobox-store install <core>_libretro`. Cores of an older install, inside
# app/, are moved to cores/.
#
#   RETROARCH_CFLAGS   optimization flags of a source build (default:
#                      -O3 -march=native -pipe). They only apply to the
#                      frontend: the cores are the buildbot's builds.
EMULATOR="retroarch"
LABEL="RetroArch"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly BUILDBOT="https://buildbot.libretro.com"
# mupen64plus_next and flycast are built from source on ARM (build_arm_cores):
# the buildbot's are GLES builds and RetroArch is built against desktop OpenGL
# there. retrobox.cores.BUILT_ON_ARM never offers them for download on ARM.
readonly CORES_DIR="${INSTALL_DIR}/cores"

function share_dir() {
    echo "${STAGE}/share/retroarch"
}

# The cores of an older install were in app/share/retroarch/cores: keep them.
function move_legacy_cores() {
    local legacy="${APP_DIR}/share/retroarch/cores"
    compgen -G "${CORES_DIR}/*_libretro.so" >/dev/null && return 0
    compgen -G "${legacy}/*_libretro.so" >/dev/null || return 0
    mkdir -p "${CORES_DIR}"
    mv "${legacy}"/*_libretro.so "${CORES_DIR}/"
    log_info "Moved the cores of the previous install to ${CORES_DIR}."
}

# The base cores, the first time (none installed yet), and every core's .info.
function after_install() {
    log_info "Downloading the base cores (if none is installed) and the cores' information..."
    "${_INSTALLER_ROOT}/bin/retrobox-store" install-base-cores \
        || log_warn "Some cores could not be downloaded: get them from EmulationStation's Content Downloader (libretro)."
}

function before_uninstall() {
    rm -rf "${CORES_DIR}" "${INSTALL_DIR}/info"
}

# The buildbot's frontend assets (the AppImage carries its own).
function download_assets() {
    local entry archive destination
    need unzip
    for entry in assets:assets autoconfig:autoconfig cheats:cheats \
        database-rdb:database/rdb shaders_slang:shaders overlays:overlays; do
        archive="${entry%%:*}.zip"
        destination="$(share_dir)/${entry#*:}"
        mkdir -p "${destination}"
        log_info "Assets: ${archive}"
        if curl -fsSL --retry 3 -o "${TMP_DIR}/${archive}" "${BUILDBOT}/assets/frontend/${archive}"; then
            unzip -qo "${TMP_DIR}/${archive}" -d "${destination}/"
            rm -f "${TMP_DIR}/${archive}"
        else
            log_warn "Could not download ${archive}, skipping it."
        fi
    done
}

# mupen64plus_next and flycast against desktop OpenGL, for ARM (the ones missing).
function build_arm_cores() {
    local work="${TMP_DIR}/cores" jobs=2
    mkdir -p "${work}" "${CORES_DIR}"
    if [[ ! -f "${CORES_DIR}/mupen64plus_next_libretro.so" ]]; then
        log_info "Building mupen64plus_next (desktop OpenGL)..."
        git clone --depth 1 --recurse-submodules --shallow-submodules \
            https://github.com/libretro/mupen64plus-libretro-nx.git "${work}/mupen64plus" \
            || die "Could not clone mupen64plus-libretro-nx"
        make -C "${work}/mupen64plus" -j "${jobs}" platform=unix CORE_NAME=mupen64plus_next \
            HAVE_THR_AL=1 LLE=1 HAVE_PARALLEL_RSP=1 HAVE_PARALLEL_RDP=1 \
            || die "The mupen64plus_next build failed"
        cp "${work}/mupen64plus/mupen64plus_next_libretro.so" "${CORES_DIR}/"
    fi
    if [[ ! -f "${CORES_DIR}/flycast_libretro.so" ]]; then
        log_info "Building the flycast core (desktop OpenGL)..."
        git clone --depth 1 --recurse-submodules --shallow-submodules \
            https://github.com/flyinghead/flycast.git "${work}/flycast" || die "Could not clone flycast"
        cmake -S "${work}/flycast" -B "${work}/flycast/build" -DCMAKE_BUILD_TYPE=Release \
            -DLIBRETRO=ON -DUSE_GLES=OFF -DUSE_GLES2=OFF || die "CMake could not configure flycast"
        cmake --build "${work}/flycast/build" -j "${jobs}" || die "The flycast core build failed"
        cp "${work}/flycast/build/flycast_libretro.so" "${CORES_DIR}/"
    fi
}

function install_appimage() {
    [[ "${ARCH}" == "x86_64" ]] || unavailable "The buildbot only has an x86_64 RetroArch AppImage."
    fetch "${BUILDBOT}/nightly/linux/x86_64/RetroArch.7z" "${TMP_DIR}/RetroArch.7z"
    extract_archive "${TMP_DIR}/RetroArch.7z" "${TMP_DIR}/RetroArch"
    local appimage home
    appimage="$(find "${TMP_DIR}/RetroArch" -maxdepth 2 -name '*.AppImage' -type f | head -n 1)"
    [[ -n "${appimage}" ]] || die "RetroArch.7z holds no AppImage"
    extract_appimage "${appimage}"
    # the program is in usr/ (bin, lib, share): it becomes the top of app/,
    # where the generator reads share/retroarch from
    [[ -d "${STAGE}/usr" ]] || die "The RetroArch AppImage has no usr/ folder"
    mv "${STAGE}" "${TMP_DIR}/appdir"
    mv "${TMP_DIR}/appdir/usr" "${STAGE}"
    # its portable home: assets, autoconfig, database, shaders, overlays...
    home="${appimage}.home/.config/retroarch"
    if [[ -d "${home}" ]]; then
        mkdir -p "$(share_dir)"
        cp -a "${home}/." "$(share_dir)/"
        rm -f "$(share_dir)/retroarch.cfg"
    fi
    require_executable bin/retroarch
    move_legacy_cores
}

function install_source() {
    install_packages \
        "build-essential git make pkg-config unzip curl libsdl2-dev libvulkan-dev
         libx11-xcb-dev libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev
         libfreetype6-dev libxml2-dev libavcodec-dev libavformat-dev libavutil-dev
         libswresample-dev libswscale-dev libopenal-dev libsndfile1-dev
         libusb-1.0-0-dev libudev-dev libasound2-dev libpipewire-0.3-dev cmake" \
        "gcc-c++ git make pkgconf-pkg-config unzip curl SDL2-devel vulkan-loader-devel
         vulkan-headers mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel
         freetype-devel libxml2-devel ffmpeg-devel openal-soft-devel libsndfile-devel
         libusb1-devel systemd-devel alsa-lib-devel pipewire-devel cmake"
    local flags="${RETROARCH_CFLAGS:--O3 -march=native -pipe}" root="${TMP_DIR}/root"
    git_clone https://github.com/libretro/RetroArch.git
    log_info "Building RetroArch with ${JOBS} jobs..."
    (
        cd "${SRC_DIR}"
        CFLAGS="${flags}" CXXFLAGS="${flags}" ./configure --prefix="${FINAL_APP_DIR}" \
            --enable-opengl --enable-vulkan --enable-pipewire --enable-alsa \
            --enable-networking --enable-discord --enable-cheevos --enable-ssl
        make -j "${JOBS}"
        make install DESTDIR="${root}"
    ) || die "The RetroArch build failed: check the messages above"
    cp -a "${root}${FINAL_APP_DIR}/." "${STAGE}/"
    require_executable bin/retroarch
    move_legacy_cores
    [[ "${ARCH}" == "x86_64" ]] || build_arm_cores
    download_assets
    remove_sources
}

installer_main "$@"
