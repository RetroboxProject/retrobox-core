#!/usr/bin/env bash
## DOLPHIN INSTALLER
## Created: 1 November 2025
## Changed: 4 August 2026 (rewritten in the style of the other installers;
##   the source install now uses "cmake --install" with a prefix inside
##   INSTALL_DIR/app, so it is self-contained and does not depend on the git
##   clone still existing)
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/dolphin-emu"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
DOLPHIN_SRC="${SRC_DIR}/dolphin-emu"
TMP_DIR="$(mktemp -d)"
ARCH="$(uname -m)"

# Third-party AppImage (official Dolphin does not publish its own AppImage)
APPIMAGE_REPO="pkgforge-dev/Dolphin-emu-AppImage"
APPIMAGE_API_URL="https://api.github.com/repos/${APPIMAGE_REPO}/releases/latest"

# Official repo, to build from source
SOURCE_UPSTREAM="https://github.com/dolphin-emu/dolphin.git"

## FUNCTIONS

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function uninstall() {
  rm -r "${INSTALL_DIR}"
}

function appimage_install(){
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "The Dolphin AppImage is only available for x86_64 (detected architecture: ${ARCH})"
  fi

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi

  echo "[INFO] Looking for the latest Dolphin AppImage on GitHub..."
  DOWNLOAD_URL=$(curl -s "${APPIMAGE_API_URL}" | grep x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n1)

  if [[ -z "${DOWNLOAD_URL}" ]]; then
    error "Could not get the AppImage download URL from GitHub"
  fi

  mkdir -p "${INSTALL_DIR}"

  echo "[INFO] Downloading: ${DOWNLOAD_URL}"
  curl -L "${DOWNLOAD_URL}" -o "${TMP_DIR}/dolphin.AppImage"
  chmod +x "${TMP_DIR}/dolphin.AppImage"

  echo "[INFO] Extracting the AppImage..."
  (
    cd "${TMP_DIR}" || exit 1
    ./dolphin.AppImage --appimage-extract >/dev/null 2>&1
    mv AppDir "${INSTALL_DIR}/app"
  )

  rm -rf "${TMP_DIR}"
  echo "[INFO] Installation (extracted AppImage) completed."
}

function check_deps() {
  echo "[INFO] Checking build dependencies..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake ninja-build git \
      pkgconf-pkg-config mesa-libGL-devel libX11-devel libXrandr-devel libXi-devel \
      mesa-libEGL-devel ffmpeg-devel systemd-devel libevdev-devel \
      SDL3-devel fmt-devel glslang-devel pugixml-devel enet-devel xxhash-devel \
      bzip2-devel xz-devel libzstd-devel zlib-devel minizip-ng-devel lzo-devel lz4-devel \
      libspng-devel cubeb-devel libusb1-devel miniupnpc-devel libcurl-devel hidapi-devel \
      gtest-devel alsa-lib-devel pulseaudio-libs-devel llvm-devel bluez-libs-devel \
      qt6-qtbase-devel qt6-qtbase-private-devel qt6-qtsvg-devel gettext \
      || error "Could not install the build dependencies (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake ninja-build git \
      pkg-config libgl1-mesa-dev libx11-dev libxrandr-dev libxi-dev \
      libegl1-mesa-dev libavcodec-dev libavformat-dev libavutil-dev \
      libswresample-dev libswscale-dev libudev-dev libevdev-dev \
      libsdl3-dev libfmt-dev glslang-dev glslang-tools libpugixml-dev libenet-dev libxxhash-dev \
      libbz2-dev liblzma-dev libzstd-dev zlib1g-dev libminizip-ng-dev liblzo2-dev liblz4-dev \
      libspng-dev libcubeb-dev libusb-1.0-0-dev libminiupnpc-dev libcurl4-openssl-dev libhidapi-dev \
      libgtest-dev libasound2-dev libpulse-dev llvm-dev libbluetooth-dev \
      qt6-base-dev qt6-base-private-dev qt6-svg-dev gettext librsvg2-bin \
      || error "Could not install the build dependencies (apt)"
  fi
}

function cmake_extra_flags() {
  # Fedora and Debian/Ubuntu don't ship compatible versions of SFML 3.x,
  # MbedTLS 2.x or a recent libmgba, so they are vendored, as the official
  # package does. Debian also needs minizip-ng vendored (it is only in
  # "testing" in its repo).
  if command -v dnf &> /dev/null; then
    echo "-DUSE_SYSTEM_SFML=OFF -DUSE_SYSTEM_MBEDTLS=OFF -DUSE_SYSTEM_LIBMGBA=OFF"
  else
    echo "-DUSE_SYSTEM_MINIZIP-NG=OFF -DUSE_SYSTEM_SFML=OFF -DUSE_SYSTEM_MBEDTLS=OFF -DUSE_SYSTEM_LIBMGBA=OFF"
  fi
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Cloning Dolphin (this may take a while, the repo is big)..."
  git clone --recursive "${SOURCE_UPSTREAM}" "${DOLPHIN_SRC}"

  local extra_flags
  extra_flags="$(cmake_extra_flags)"

  echo "[INFO] Configuring and building (install prefix: ${INSTALL_DIR}/app)..."
  mkdir -p "${DOLPHIN_SRC}/build"
  (
    cd "${DOLPHIN_SRC}/build" || exit 1
    # shellcheck disable=SC2086
    cmake .. -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}/app" \
      ${extra_flags} \
      || exit 1
    ninja || exit 1
    ninja install || exit 1
  ) || error "Failed to build/install Dolphin. Check the cmake/ninja output above"

  # "ninja install" puts bin/dolphin-emu and share/dolphin-emu/{sys,...} inside
  # the prefix, with the data path already resolved to an absolute one at build
  # time: the result in INSTALL_DIR/app is self-contained and does not depend
  # on _src/
  [[ -x "${INSTALL_DIR}/app/bin/dolphin-emu" ]] \
    || error "The build finished but the installed binary is not in ${INSTALL_DIR}/app/bin/dolphin-emu"

  echo "[INFO] Cleaning up temporary sources..."
  rm -rf "${SRC_DIR}"
  echo "[INFO] Build from source completed. Binary: ${INSTALL_DIR}/app/bin/dolphin-emu"
}

## ENTRY POINT
case "$1" in
"-i") appimage_install;;
"-s") install_source;;
"-u"|"-d") uninstall;;
*)  exit 1;;
esac

exit 0