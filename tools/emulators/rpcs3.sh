#!/usr/bin/env bash
## RPCS3 INSTALLER
## Created: 4 August 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/rpcs3"
TMP_DIR="$(mktemp -d)"
REPO="RPCS3/rpcs3-binaries-linux"
API_URL="https://api.github.com/repos/$REPO/releases"
ARCH="$(uname -m)"

## FUNCTIONS

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function uninstall() {
  rm -r "${INSTALL_DIR}"
}

function appimage_install(){
  # For now RPCS3 only publishes a Linux AppImage for x86_64 ("linux64")
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "RPCS3 only distributes a Linux AppImage for x86_64 for now (detected architecture: ${ARCH})"
  fi

  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi
  if ! command -v jq &> /dev/null; then
    sudo dnf install -y jq || sudo apt-get install -y jq
  fi

  # The AppImage name carries the version, build and commit hash
  # (e.g. rpcs3-v0.0.39-18703-abcdef01_linux64.AppImage), so it has to be
  # resolved against the latest release instead of building the URL by hand.
  releases=$(curl -sL "${API_URL}?per_page=5")
  APPIMAGE_URL=$(echo "$releases" | jq -r '
    .[0].assets[] | select(.name | endswith("_linux64.AppImage")) | .browser_download_url
  ' | head -n1)

  if [[ -z "${APPIMAGE_URL}" ]]; then
    error "No linux64 AppImage found in the latest available release"
  fi

  mkdir -p "${INSTALL_DIR}"

  echo "[INFO] Downloading $(basename "${APPIMAGE_URL}")..."
  curl -L "${APPIMAGE_URL}" -o "${TMP_DIR}/rpcs3.AppImage"

  mv "${TMP_DIR}/rpcs3.AppImage" "${INSTALL_DIR}/rpcs3.AppImage"
  chmod +x "${INSTALL_DIR}/rpcs3.AppImage"

  echo "[INFO] Extracting the AppImage..."
  (
    cd "${INSTALL_DIR}" || exit 1
    "${INSTALL_DIR}/rpcs3.AppImage" --appimage-extract >/dev/null 2>&1
    mv "${INSTALL_DIR}/squashfs-root" "${INSTALL_DIR}/app"
    rm "${INSTALL_DIR}/rpcs3.AppImage"
  )

  rm -rf "${TMP_DIR}"
  echo "[INFO] Installation completed."
}

## ENTRY POINT
case "$1" in
"-i") appimage_install;;
"-u"|"-d") uninstall;;
*)  exit 1;;
esac

exit 0