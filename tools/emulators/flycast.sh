#!/usr/bin/env bash
## FLYCAST (STANDALONE) INSTALLER
## Created: 23 August 2026
## Builds standalone flycast from source for any architecture your toolchain
## supports (mainly meant for x86_64 and aarch64). It also keeps the download
## of the official AppImage (x86_64 only) and the uninstall, inherited from the
## previous version of this script.
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
GITHUB_REPO="flyinghead/flycast"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/flycast"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
FLYCAST_SRC="${SRC_DIR}/flycast"
SOURCE_UPSTREAM="https://github.com/flyinghead/flycast.git"
ARCH="$(uname -m)"

# Optimization flags for the build itself. -march=native assumes you build on
# the same machine/board you will run flycast on (no cross-compiling); if that
# is not your case, edit this variable before running -s.
EXTRA_CFLAGS="-O3 -march=native -pipe"

# Number of build jobs. Can be overridden with the JOBS environment variable
# (useful on ARM boards with little RAM, where a full "nproc" can run out of
# memory while linking the heaviest files, e.g. the Vulkan renderer).
JOBS="${JOBS:-$(nproc)}"

## FUNCTIONS

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function uninstall() {
  rm -rf "${INSTALL_DIR}/app"
}

function check_deps() {
  echo "[INFO] Checking build dependencies..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake make git pkgconf-pkg-config \
      SDL2-devel vulkan-loader-devel vulkan-headers \
      mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel libX11-devel \
      libpng-devel libzip-devel libcurl-devel \
      alsa-lib-devel pipewire-devel libevdev-devel \
      || error "Could not install the build dependencies (dnf)"
  else
    sudo apt-get install -y \
      build-essential cmake make git pkg-config \
      libsdl2-dev libvulkan-dev \
      libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev \
      libpng-dev libzip-dev libcurl4-openssl-dev \
      libasound2-dev libpipewire-0.3-dev libevdev-dev \
      || error "Could not install the build dependencies (apt)"
  fi
  # This list is a best guess (it does not come from an official flycast
  # requirements list). If cmake complains about a missing library while
  # configuring, install the matching -dev/-devel package and run -s again.
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Detected architecture: ${ARCH}"
  echo "[INFO] Cloning flycast..."
  [[ -d "${FLYCAST_SRC}" ]] && rm -rf "${FLYCAST_SRC}"
  git clone "${SOURCE_UPSTREAM}" "${FLYCAST_SRC}" \
    || error "Failed to clone flycast"

  echo "[INFO] Initializing submodules (takes a while, flycast has several)..."
  (
    cd "${FLYCAST_SRC}" || exit 1
    git submodule update --init --recursive
  ) || error "Failed to initialize the flycast submodules"

  echo "[INFO] Configuring and building (arch: ${ARCH}, ${JOBS} jobs)..."
  (
    cd "${FLYCAST_SRC}" || exit 1
    mkdir -p build && cd build || exit 1
    CFLAGS="${EXTRA_CFLAGS}" CXXFLAGS="${EXTRA_CFLAGS}" cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      || exit 1
    cmake --build . -j"${JOBS}" || exit 1
  ) || error "Failed to build flycast. Check the cmake/make output above"

  local bin_out="${FLYCAST_SRC}/build/flycast"
  [[ -x "${bin_out}" ]] \
    || error "The build finished but the binary is not in ${bin_out} (this version's CMakeLists may name it differently; look inside ${FLYCAST_SRC}/build)"

  echo "[INFO] Installing into ${INSTALL_DIR}/app..."
  mkdir -p "${INSTALL_DIR}/app/bin"
  cp "${bin_out}" "${INSTALL_DIR}/app/bin/flycast"

  echo "[INFO] Cleaning up temporary sources..."
  rm -rf "${SRC_DIR}"

  echo "[INFO] Installation from source completed. Binary: ${INSTALL_DIR}/app/bin/flycast"
  echo "[INFO] Note: the standalone flycast config/BIOS/etc are NOT stored here,"
  echo "[INFO] but in \$HOME/.local/share/flycast or \$HOME/.config/flycast (depending on the distro)."
}

function install_appimage() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "The official flycast AppImage is only published for x86_64 (detected architecture: ${ARCH}); use -s to build from source"
  fi

  echo "[INFO] Looking for the latest Flycast AppImage (x86_64) on GitHub..."
  local download_url
  download_url=$(curl -s "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" \
    | grep -i x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

  [[ -n "${download_url}" ]] || error "Could not get the AppImage download URL from GitHub"

  echo "[INFO] Downloading: ${download_url}"
  mkdir -p "${INSTALL_DIR}/app/bin" "${INSTALL_DIR}/config"
  curl -fL "${download_url}" -o "${INSTALL_DIR}/app/bin/flycast.AppImage" \
    || error "Error while downloading the AppImage"

  chmod +x "${INSTALL_DIR}/app/bin/flycast.AppImage"
  echo "[INFO] AppImage installation completed. Binary: ${INSTALL_DIR}/app/bin/flycast.AppImage"
}

## ENTRY POINT

case "$1" in
"-s") install_source;;
"-i") install_appimage;;
"-u"|"-d") uninstall;;
*)
  echo "Usage: $0 [-s | -i | -u]"
  echo "  -s : Build standalone flycast from source (any architecture; meant for x86_64/aarch64)"
  echo "  -i : Install the official AppImage (x86_64 only, from GitHub)"
  echo "  -u : Uninstall"
  exit 1
  ;;
esac

exit 0