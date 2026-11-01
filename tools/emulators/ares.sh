#!/usr/bin/env bash
## ARES INSTALLER (+ librashader)
## Created: 3 August 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/ares"
SRC_DIR="${RETROBOX_EMULATORS_DIR}/_src"
ARES_SRC="${SRC_DIR}/ares"
LIBRASHADER_SRC="${SRC_DIR}/librashader"
ARES_REPO="https://github.com/ares-emulator/ares.git"
LIBRASHADER_REPO="https://github.com/SnowflakePowered/librashader.git"

## FUNCTIONS

function error() {
  echo "[ERROR] $*."
  exit 1
}

function ares_uninstall() {
  rm -r "${INSTALL_DIR}"
}

function check_deps() {
  local -a pkgs=(
    git cmake ninja-build build-essential pkg-config
    libsdl3-dev libgtk-3-dev libx11-dev libxext-dev libice-dev
    libgl-dev libglu1-mesa-dev
  )
  echo "[INFO] Checking build dependencies..."
  sudo apt-get install -y "${pkgs[@]}"

  if ! command -v rustup &> /dev/null; then
    error "rustup is not installed. librashader needs a nightly Rust toolchain. Install it from https://rustup.rs and run the script again"
  fi
  rustup toolchain list | grep -q '^nightly' || rustup toolchain install nightly
}

function build_ares() {
  echo "[INFO] Cloning ares..."
  git clone --depth 1 "${ARES_REPO}" "${ARES_SRC}"

  echo "[INFO] Building ares..."
  cmake -S "${ARES_SRC}" -B "${ARES_SRC}/build" -G Ninja \
    -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}" \
    -DCMAKE_BUILD_TYPE=Release
  ninja -C "${ARES_SRC}/build"

  echo "[INFO] Installing ares into ${INSTALL_DIR}..."
  ninja -C "${ARES_SRC}/build" install

  # Safety net: if CMake's install() does not put sourcery/ares in bin/,
  # look for them in the build tree and copy them by hand.
  mkdir -p "${INSTALL_DIR}/bin"
  for bin in ares sourcery; do
    if [[ ! -x "${INSTALL_DIR}/bin/${bin}" ]]; then
      local found
      found="$(find "${ARES_SRC}/build" -maxdepth 4 -type f -name "${bin}" -perm -u+x | head -n1)"
      [[ -n "${found}" ]] && cp "${found}" "${INSTALL_DIR}/bin/${bin}"
    fi
  done
}

function build_librashader() {
  echo "[INFO] Cloning librashader..."
  git clone --depth 1 "${LIBRASHADER_REPO}" "${LIBRASHADER_SRC}"

  echo "[INFO] Building librashader (nightly, optimized profile)..."
  (
    cd "${LIBRASHADER_SRC}"
    rustup run nightly cargo run -p librashader-build-script -- --profile optimized
  )

  local so_file
  so_file="$(find "${LIBRASHADER_SRC}/target" -maxdepth 2 -type f -name 'librashader.so' | head -n1)"
  [[ -n "${so_file}" ]] || error "librashader.so was not produced by the build"

  mkdir -p "${INSTALL_DIR}/lib"
  cp "${so_file}" "${INSTALL_DIR}/lib/librashader.so"
}

function ares_source_inst() {
  mkdir -p "${INSTALL_DIR}" "${SRC_DIR}"
  check_deps
  build_ares
  build_librashader

  echo "[INFO] Cleaning up temporary sources..."
  rm -rf "${SRC_DIR}"

  echo "[INFO] Installation completed."
}

## ENTRY POINT
case "$1" in
  "-s") ares_source_inst;;
  "-u") ares_uninstall;;
  *)  exit 1;;
esac

exit 0