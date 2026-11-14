#!/usr/bin/env bash
## RETROARCH INSTALLER
## Created: 4 August 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/retroarch"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
RETROARCH_SRC="${SRC_DIR}/RetroArch"
TMP_DIR="$(mktemp -d)"
SOURCE_UPSTREAM="https://github.com/libretro/RetroArch.git"
MUPEN64_NEXT_UPSTREAM="https://github.com/libretro/mupen64plus-libretro-nx.git"
FLYCAST_UPSTREAM="https://github.com/flyinghead/flycast.git"
ARCH="$(uname -m)"

# Optimization flags for the frontend itself (Ryzen 7 7435HS). NOTE: this does
# NOT optimize the cores: they are prebuilt .so files downloaded from the
# buildbot further down, not built here. If a given core (FBNeo,
# Mupen64Plus-Next...) stutters, the fix is to build THAT core, not the frontend.
EXTRA_CFLAGS="-O3 -march=native -pipe"

# Cores to download from the official buildbot in the source install.
# Exact name = the one shown in
# https://buildbot.libretro.com/nightly/linux/x86_64/latest/ without the "_libretro.so.zip" suffix
CORES=(
  fbneo
  mupen64plus_next
  # add the rest of the cores you use here
)

# Cores that are built separately on non-x64 (compile_<core>_from_source)
# instead of using the buildbot's prebuilt .so, because of a GL/GLES context
# clash between how that core is built and how the frontend is configured on
# that architecture.
CORES_BUILT_FROM_SOURCE_NON_X64=(
  mupen64plus_next
  flycast
)

## FUNCTIONS

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function uninstall() {
  rm -r "${INSTALL_DIR}/app"
}

function check_deps() {
  echo "[INFO] Checking build dependencies..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake make git pkgconf-pkg-config \
      SDL2-devel vulkan-loader-devel vulkan-headers \
      mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel \
      freetype-devel libxml2-devel \
      ffmpeg-devel \
      openal-soft-devel libsndfile-devel libusb1-devel \
      systemd-devel alsa-lib-devel pipewire-devel \
      || error "Could not install the build dependencies (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake make git unzip 7zip curl pkg-config \
      libsdl2-dev libsdl2-mixer-dev libvulkan-dev libx11-xcb-dev \
      libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev \
      libfreetype6-dev libxml2-dev \
      libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
      libopenal-dev libsndfile1-dev libusb-1.0-0-dev \
      libudev-dev libasound2-dev libpipewire-0.3-dev \
      || error "Could not install the build dependencies (apt)"
  fi
}

function check_deps_appimage() {
  echo "[INFO] Checking the dependencies of the AppImage install..."
  local missing=()
  command -v curl &> /dev/null || missing+=(curl)
  command -v 7z &> /dev/null || missing+=(7z)

  if [[ ${#missing[@]} -eq 0 ]]; then
    return
  fi

  if command -v dnf &> /dev/null; then
    sudo dnf install -y curl p7zip p7zip-plugins \
      || error "Could not install the dependencies of the AppImage install (dnf)"
  else
    sudo apt-get install -y curl p7zip-full \
      || error "Could not install the dependencies of the AppImage install (apt)"
  fi
}

# Builds mupen64plus_next from source instead of using the buildbot's prebuilt
# .so (GL/GLES context clash on non-x64).
function compile_mupen64_next_from_source() {
  echo "[INFO] Building mupen64plus_next from source (platform=unix, desktop OpenGL, RDP: GLideN64+angrylion+parallel, RSP: HLE+cxd4+parallel)..."
  local core_src="${SRC_DIR}/mupen64plus-libretro-nx"
  [[ -d "${core_src}" ]] && rm -rf "${core_src}"
  git clone --depth 1 --shallow-submodules --recursive "${MUPEN64_NEXT_UPSTREAM}" "${core_src}"

  local jobs
  jobs="$(nproc)"
  [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]] && jobs=2

  local m64p_flags=(platform=unix CORE_NAME=mupen64plus_next HAVE_THR_AL=1 LLE=1 HAVE_PARALLEL_RSP=1 HAVE_PARALLEL_RDP=1)

  (
    cd "${core_src}" || exit 1
    make "${m64p_flags[@]}" clean
    make "${m64p_flags[@]}" -j"${jobs}"
  ) || error "Failed to build mupen64plus_next from source"

  [[ -f "${core_src}/mupen64plus_next_libretro.so" ]] \
    || error "The mupen64plus_next build finished but mupen64plus_next_libretro.so is missing"

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  cp "${core_src}/mupen64plus_next_libretro.so" "${INSTALL_DIR}/app/share/retroarch/cores/"
}

# Builds flycast from source against desktop OpenGL (-DUSE_GLES=OFF), in case
# the buildbot's .so for this arch is built GLES-only and does not match the
# frontend (same pattern as mupen64plus_next, but with CMake instead of a Makefile).
function compile_flycast_from_source() {
  echo "[INFO] Building flycast from source (CMake, desktop OpenGL, no GLES)..."
  local core_src="${SRC_DIR}/flycast"
  [[ -d "${core_src}" ]] && rm -rf "${core_src}"
  git clone --depth 1 --recursive "${FLYCAST_UPSTREAM}" "${core_src}"

  local jobs
  jobs="$(nproc)"
  [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]] && jobs=2

  (
    cd "${core_src}" || exit 1
    mkdir -p build && cd build || exit 1
    cmake .. -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON -DUSE_GLES=OFF -DUSE_GLES2=OFF \
      || exit 1
    cmake --build . -j"${jobs}" || exit 1
  ) || error "Failed to build flycast from source"

  [[ -f "${core_src}/build/flycast_libretro.so" ]] \
    || error "The flycast build finished but flycast_libretro.so is missing"

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  cp "${core_src}/build/flycast_libretro.so" "${INSTALL_DIR}/app/share/retroarch/cores/"
}

function download_cores() {
  # Detected architecture -> buildbot folder
  local buildbot_arch=""
  case "${ARCH}" in
    x86_64|amd64)
      buildbot_arch="x86_64"
      ;;
    aarch64|arm64)
      buildbot_arch="aarch64"
      ;;
    armv7l|armhf)
      buildbot_arch="armhf"
      ;;
    i686|i386|x86)
      buildbot_arch="x86"
      ;;
    *)
      echo "[WARN] Architecture not supported for downloading cores (detected: ${ARCH}); skipping."
      return
      ;;
  esac

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"

  local base="https://buildbot.libretro.com/nightly/linux/${buildbot_arch}/latest"

  echo "[INFO] Getting the list of available cores from the buildbot (${buildbot_arch})..."

  # Download the HTML index, keep the .so.zip files and strip them down to the core name
  local cores_list
  cores_list=$(curl -sfL "${base}/" | grep -oE '[a-zA-Z0-9_\-]+_libretro\.so\.zip' | sed -E 's/_libretro\.so\.zip//' | sort -u)

  if [[ -z "${cores_list}" ]]; then
    echo "[WARN] Could not get the list of cores from the buildbot."
    return
  fi

  local core skip
  for core in ${cores_list}; do
    # On non-x64 these cores are built separately (see CORES_BUILT_FROM_SOURCE_NON_X64)
    # because of the GL/GLES context clash between the prebuilt .so and the frontend.
    skip=0
    if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
      for c in "${CORES_BUILT_FROM_SOURCE_NON_X64[@]}"; do
        [[ "${core}" == "${c}" ]] && skip=1 && break
      done
    fi
    if [[ "${skip}" -eq 1 ]]; then
      echo "[INFO] Skipping the prebuilt ${core} (it is built from source on this architecture)."
      continue
    fi
    echo "[INFO] Downloading core: ${core}..."
    if ! curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      echo "[WARN] Could not download the core '${core}', skipping"
      continue
    fi
    unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
    rm -f "${TMP_DIR}/${core}.zip"
  done
}

function download_selected_cores() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    echo "[WARN] Downloading cores is only supported on x86_64 for now (detected architecture: ${ARCH}); skipping."
    return
  fi

  mkdir -p "${INSTALL_DIR}/cores"
  local base="https://buildbot.libretro.com/nightly/linux/x86_64/latest"

  for core in "${CORES[@]}"; do
    echo "[INFO] Downloading core: ${core}..."
    if ! curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      echo "[WARN] Could not download the core '${core}', skipping"
      continue
    fi
    unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
    rm -f "${TMP_DIR}/${core}.zip"
  done
}

function download_frontend_assets() {
  local base="https://buildbot.libretro.com/assets/frontend"

  local zip dest
  for entry in \
    "info.zip:${INSTALL_DIR}/app/share/retroarch/cores" \
    "assets.zip:${INSTALL_DIR}/app/share/retroarch/assets" \
    "autoconfig.zip:${INSTALL_DIR}/app/share/retroarch/autoconfig" \
    "cheats.zip:${INSTALL_DIR}/app/share/retroarch/cheats" \
    "database-rdb.zip:${INSTALL_DIR}/app/share/retroarch/database/rdb" \
    "shaders_slang.zip:${INSTALL_DIR}/app/share/retroarch/shaders" \
    "overlays.zip:${INSTALL_DIR}/app/share/retroarch/overlays"
  do
    zip="${entry%%:*}"
    dest="${entry#*:}"
    mkdir -p "${dest}"
    echo "[INFO] Downloading ${zip}..."
    if ! curl -sfL "${base}/${zip}" -o "${TMP_DIR}/${zip}"; then
      echo "[WARN] Could not download ${zip}, skipping"
      continue
    fi
    unzip -qo "${TMP_DIR}/${zip}" -d "${dest}/"
    rm -f "${TMP_DIR}/${zip}"
  done
}

function generate_config() {
  if [[ -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
    echo "[INFO] ${INSTALL_DIR}/config/retroarch.cfg already exists; not overwriting it (so hand-made changes are kept)."
    return
  fi

  mkdir -p "${INSTALL_DIR}/config/retroarch"
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Cloning RetroArch..."
  git clone --recursive "${SOURCE_UPSTREAM}" "${RETROARCH_SRC}"

  echo "[INFO] Configuring with desktop OpenGL"
  local gl_flags=(--enable-opengl)
  echo "[INFO] Configuring and building (prefix: ${INSTALL_DIR}/app)..."

  (
    cd "${RETROARCH_SRC}" || exit 1
    CFLAGS="${EXTRA_CFLAGS}" CXXFLAGS="${EXTRA_CFLAGS}" ./configure \
      --prefix="${INSTALL_DIR}/app" \
      "${gl_flags[@]}" \
      --enable-vulkan --enable-pipewire --enable-alsa --enable-networking --enable-discord \
      --enable-cheevos --enable-ssl \
      || exit 1
    make -j"$(nproc)" || exit 1
    make install || exit 1
  ) || error "Failed to build/install RetroArch. Check the configure/make output above"

  # "make install" with --prefix puts bin/retroarch in a self-contained tree;
  # the result in INSTALL_DIR/app does not depend on _src/ still existing.
  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] \
    || error "The build finished but the installed binary is not in ${INSTALL_DIR}/app/bin/retroarch"

  download_cores

  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    compile_mupen64_next_from_source
    compile_flycast_from_source
  fi

  download_frontend_assets
  generate_config

  echo "[INFO] Cleaning up temporary sources..."
  rm -rf "${SRC_DIR}" "${TMP_DIR}"
  echo "[INFO] Installation from source completed. Binary: ${INSTALL_DIR}/app/bin/retroarch"
  echo "[INFO] Config: ${INSTALL_DIR}/config/retroarch.cfg — run it with: ${INSTALL_DIR}/app/bin/retroarch -c ${INSTALL_DIR}/config/retroarch.cfg"
}

function install_appimage() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "The AppImage install is only supported on x86_64 for now (detected architecture: ${ARCH})"
  fi

  uninstall 2>/dev/null || true
  check_deps_appimage

  local url="https://buildbot.libretro.com/nightly/linux/x86_64/RetroArch.7z"
  local archive="${TMP_DIR}/RetroArch.7z"
  local extract_dir="${TMP_DIR}/extracted"

  echo "[INFO] Downloading the RetroArch AppImage..."
  curl -fSL -o "${archive}" "${url}" || error "Could not download the RetroArch AppImage"

  echo "[INFO] Extracting ${archive}..."
  mkdir -p "${extract_dir}"
  7z x -y -o"${extract_dir}" "${archive}" >/dev/null \
    || error "Failed to extract the downloaded .7z"

  local appimage="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage"
  [[ -f "${appimage}" ]] || error "The AppImage was not found after extracting"
  chmod +x "${appimage}"

  echo "[INFO] Unpacking the AppImage (--appimage-extract)..."
  (
    cd "${extract_dir}" || exit 1
    "${appimage}" --appimage-extract >/dev/null 2>&1 || exit 1
  ) || error "Failed to unpack the AppImage"

  # The binary and friends live in squashfs-root/usr (bin/, lib/, share/), not
  # at the root of squashfs-root (which only holds the AppRun, the .desktop and the icon).
  [[ -d "${extract_dir}/squashfs-root/usr" ]] \
    || error "Unexpected squashfs-root layout: there is no usr/ inside"

  mkdir -p "${INSTALL_DIR}/app"
  cp -r "${extract_dir}/squashfs-root/usr"/* "${INSTALL_DIR}/app"
  cp -r "${extract_dir}/squashfs-root/AppRun" "${INSTALL_DIR}/app"

  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] \
    || error "The AppImage was unpacked but the binary is not in ${INSTALL_DIR}/app/bin/retroarch"

  # The AppImage brings its own "portable" config in .home/.config/retroarch
  # (cores, assets, autoconfig, cheats, database, shaders, overlays, retroarch.cfg...).
  # It is merged into the same layout the source install uses
  # (INSTALL_DIR/app/share/retroarch) instead of being left in a separate directory.
  local home_cfg="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch"
  if [[ -d "${home_cfg}" ]]; then
    echo "[INFO] Merging the AppImage's embedded configuration into ${INSTALL_DIR}/app/share/retroarch..."
    mkdir -p "${INSTALL_DIR}/app/share/retroarch"
    cp -r "${home_cfg}"/* "${INSTALL_DIR}/app/share/retroarch/"
  fi

  # As in the source install, the final retroarch.cfg lives in
  # INSTALL_DIR/config/retroarch.cfg. If the AppImage brought one and there is
  # none there yet, it is promoted; if one already exists (a previous install
  # edited by hand), it is kept.
  mkdir -p "${INSTALL_DIR}/config"
  if [[ -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" ]]; then
    if [[ ! -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
      mv "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" "${INSTALL_DIR}/config/retroarch.cfg"
    else
      rm -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg"
    fi
  fi
  generate_config

  echo "[INFO] Cleaning up temporary files..."
  rm -rf "${extract_dir}" "${archive}"

  # As in the source install: the cores are downloaded from the libretro
  # buildbot instead of using the AppImage's RetroArch_cores.7z.
  download_cores

  rm -rf "${TMP_DIR}"
  echo "[INFO] AppImage installation completed. Binary: ${INSTALL_DIR}/app/bin/retroarch"
  echo "[INFO] Config: ${INSTALL_DIR}/config/retroarch.cfg — run it with: ${INSTALL_DIR}/app/bin/retroarch -c ${INSTALL_DIR}/config/retroarch.cfg"
}

## ENTRY POINT
case "$1" in
"-s") install_source;;
"-a") install_appimage;;
"-u"|"-d") uninstall;;
*)  exit 1;;
esac

exit 0
