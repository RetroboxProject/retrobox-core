#!/usr/bin/env bash
# RetroArch: the nightly AppImage of the libretro buildbot (x86_64), or a
# build from source. Both install the frontend under app/ (bin/retroarch,
# share/retroarch/{cores,assets,...}) and the cores of the buildbot nightly.
#
#   RETROARCH_CFLAGS   optimization flags of a source build (default:
#                      -O3 -march=native -pipe). They only apply to the
#                      frontend: the cores are the buildbot's builds.
EMULATOR="retroarch"
LABEL="RetroArch"
# shellcheck source=tools/lib/installer.sh
source "$(dirname "$(readlink -f "$0")")/../lib/installer.sh"

readonly BUILDBOT="https://buildbot.libretro.com"
# Built from source instead of the buildbot's .so on ARM: those are GLES
# builds and RetroArch is built against desktop OpenGL there.
readonly CORES_BUILT_ON_ARM=(mupen64plus_next flycast)

function share_dir() {
    echo "${STAGE}/share/retroarch"
}

function buildbot_arch() {
    case "${ARCH}" in
        x86_64 | aarch64) echo "${ARCH}" ;;
        armv7l | armhf) echo "armhf" ;;
        i686 | i386) echo "x86" ;;
        *) return 1 ;;
    esac
}

function built_on_arm() {
    local core
    [[ "${ARCH}" == "x86_64" ]] && return 1
    for core in "${CORES_BUILT_ON_ARM[@]}"; do
        [[ "$1" == "${core}" ]] && return 0
    done
    return 1
}

# Every core of the buildbot nightly for this architecture.
function download_cores() {
    local arch base cores core
    if ! arch="$(buildbot_arch)"; then
        log_warn "The buildbot has no cores for ${ARCH}: install them from RetroArch's menu."
        return 0
    fi
    base="${BUILDBOT}/nightly/linux/${arch}/latest"
    cores="$(curl -fsSL --retry 3 "${base}/" \
        | grep -oE '[A-Za-z0-9_-]+_libretro\.so\.zip' | sed 's/_libretro\.so\.zip$//' | sort -u || true)"
    if [[ -z "${cores}" ]]; then
        log_warn "Could not list the cores of ${base}: install them from RetroArch's menu."
        return 0
    fi
    need unzip
    mkdir -p "$(share_dir)/cores"
    for core in ${cores}; do
        built_on_arm "${core}" && continue
        log_info "Core ${core}"
        if curl -fsSL --retry 3 -o "${TMP_DIR}/core.zip" "${base}/${core}_libretro.so.zip"; then
            unzip -qo "${TMP_DIR}/core.zip" -d "$(share_dir)/cores/"
        else
            log_warn "Could not download the core ${core}, skipping it."
        fi
    done
    rm -f "${TMP_DIR}/core.zip"
}

# The buildbot's frontend assets (the AppImage carries its own).
function download_assets() {
    local entry archive destination
    need unzip
    for entry in info:cores assets:assets autoconfig:autoconfig cheats:cheats \
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

# mupen64plus_next and flycast against desktop OpenGL, for ARM.
function build_arm_cores() {
    local work="${TMP_DIR}/cores" jobs=2
    mkdir -p "${work}" "$(share_dir)/cores"
    log_info "Building mupen64plus_next (desktop OpenGL)..."
    git clone --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/libretro/mupen64plus-libretro-nx.git "${work}/mupen64plus" \
        || die "Could not clone mupen64plus-libretro-nx"
    make -C "${work}/mupen64plus" -j "${jobs}" platform=unix CORE_NAME=mupen64plus_next \
        HAVE_THR_AL=1 LLE=1 HAVE_PARALLEL_RSP=1 HAVE_PARALLEL_RDP=1 \
        || die "The mupen64plus_next build failed"
    cp "${work}/mupen64plus/mupen64plus_next_libretro.so" "$(share_dir)/cores/"

    log_info "Building the flycast core (desktop OpenGL)..."
    git clone --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/flyinghead/flycast.git "${work}/flycast" || die "Could not clone flycast"
    cmake -S "${work}/flycast" -B "${work}/flycast/build" -DCMAKE_BUILD_TYPE=Release \
        -DLIBRETRO=ON -DUSE_GLES=OFF -DUSE_GLES2=OFF || die "CMake could not configure flycast"
    cmake --build "${work}/flycast/build" -j "${jobs}" || die "The flycast core build failed"
    cp "${work}/flycast/build/flycast_libretro.so" "$(share_dir)/cores/"
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
    download_cores
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
    download_cores
    [[ "${ARCH}" == "x86_64" ]] || build_arm_cores
    download_assets
    remove_sources
}

installer_main "$@"
