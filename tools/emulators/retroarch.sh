#!/usr/bin/env bash
# RetroArch: the nightly builds of the libretro buildbot (the AppImage on
# x86_64, the bare binary on aarch64), or a build from source. All install the
# frontend under app/ (bin/retroarch, share/retroarch/{assets,autoconfig,...}).
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
readonly CORES_DIR="${INSTALL_DIR}/cores"

function share_dir() {
    echo "${STAGE}/share/retroarch"
}

# The cores of an older install were in app/share/retroarch/cores: keep them
# all (one already in cores/ wins), as retrobox.cores.migrate_legacy_cores does.
function move_legacy_cores() {
    local legacy="${APP_DIR}/share/retroarch/cores" core moved=0
    compgen -G "${legacy}/*_libretro.so" >/dev/null || return 0
    mkdir -p "${CORES_DIR}"
    for core in "${legacy}"/*_libretro.so; do
        if [[ -e "${CORES_DIR}/${core##*/}" ]]; then
            rm -f "${core}"
        else
            mv "${core}" "${CORES_DIR}/" && moved=$((moved + 1))
        fi
    done
    log_info "Moved ${moved} core(s) of the previous install to ${CORES_DIR}."
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

# The flycast core against desktop OpenGL, for ARM, when it is missing. Not the
# buildbot's: whether its aarch64 flycast runs on a desktop OpenGL RetroArch
# is still to be checked (its mupen64plus_next links libGL, so that one is
# taken from the buildbot). retrobox.cores.BUILT_ON_ARM lists the same cores.
function build_arm_cores() {
    local work="${TMP_DIR}/cores" jobs=2
    [[ -f "${CORES_DIR}/flycast_libretro.so" ]] && return 0
    mkdir -p "${work}" "${CORES_DIR}"
    log_info "Building the flycast core (desktop OpenGL)..."
    git clone --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/flyinghead/flycast.git "${work}/flycast" || die "Could not clone flycast"
    cmake -S "${work}/flycast" -B "${work}/flycast/build" -DCMAKE_BUILD_TYPE=Release \
        -DLIBRETRO=ON -DUSE_GLES=OFF -DUSE_GLES2=OFF || die "CMake could not configure flycast"
    cmake --build "${work}/flycast/build" -j "${jobs}" || die "The flycast core build failed"
    cp "${work}/flycast/build/flycast_libretro.so" "${CORES_DIR}/"
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

# The buildbot's aarch64 build: only the retroarch binary (desktop OpenGL,
# Vulkan, Wayland, X11, KMS; glibc 2.34 or newer), linked against the
# distribution's libraries, which are installed first. The assets are
# downloaded as for a source build. If a library is still missing, the next
# method (source) is tried.
function install_archive() {
    [[ "${ARCH}" == "aarch64" ]] || unavailable "The buildbot's bare RetroArch binary is only used on aarch64."
    install_packages \
        "libasound2t64|libasound2 libpulse0 libfreetype6 libfontconfig1 libwayland-egl1
         libwayland-client0 libwayland-cursor0 libx11-6 libxxf86vm1 libxinerama1 libxrandr2
         libx11-xcb1 libxcb1 libxi6 libxkbcommon0 libudev1 libgbm1 libdrm2 libgl1 libegl1
         libsdl2-2.0-0 libv4l-0t64|libv4l-0" \
        "alsa-lib pulseaudio-libs freetype fontconfig libwayland-egl libwayland-client
         libwayland-cursor libX11 libXxf86vm libXinerama libXrandr libX11-xcb libxcb libXi
         libxkbcommon systemd-libs mesa-libgbm libdrm libglvnd-glx libglvnd-egl
         sdl2-compat|SDL2 libv4l"
    fetch "${BUILDBOT}/nightly/linux/aarch64/RetroArch.7z" "${TMP_DIR}/RetroArch.7z"
    extract_archive "${TMP_DIR}/RetroArch.7z" "${TMP_DIR}/RetroArch"
    local binary missing
    binary="$(find "${TMP_DIR}/RetroArch" -name retroarch -type f | head -n 1)"
    [[ -n "${binary}" ]] || die "RetroArch.7z holds no retroarch binary"
    missing="$(ldd "${binary}" 2>&1 | awk '/not found/ { print $1 }' | tr '\n' ' ')"
    [[ -z "${missing}" ]] || unavailable "The buildbot's RetroArch needs libraries this system lacks: ${missing}"
    mkdir -p "${STAGE}/bin"
    install -m 755 "${binary}" "${STAGE}/bin/retroarch"
    require_executable bin/retroarch
    move_legacy_cores
    install_packages "build-essential git cmake" "gcc-c++ make git cmake"
    build_arm_cores
    download_assets
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
