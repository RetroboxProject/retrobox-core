#!/usr/bin/env bash
## REDREAM INSTALLER
## Created: 4 August 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/redream"
TMP_DIR="$(mktemp -d)"
DOWNLOAD_PAGE="https://redream.io/download"

## FUNCTIONS

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function uninstall() {
  rm -r "${INSTALL_DIR}/redream"
}

function tarball_install(){
  # Check curl
  if ! command -v curl &> /dev/null; then
    sudo dnf install -y curl || sudo apt-get install -y curl
  fi

  # redream has no GitHub-style API: the downloads page has to be parsed.
  # The first x86_64-linux .tar.gz link on the page is the latest "Stable
  # Release" (it comes before the "Development Releases" in the HTML).
  echo "[INFO] Looking for the latest development version in ${DOWNLOAD_PAGE}..."
  page="$(curl -sL "${DOWNLOAD_PAGE}")"

  # Cut everything before "Development Releases" so that a tarball from the
  # "Stable Releases" section is not picked by mistake
  page_dev="$(echo "${page}" | sed -n '/Development Releases/,$p')"

  TARBALL_PATH=$(echo "${page_dev}" | grep -oP '(?<=href=")/download/redream\.x86_64-linux-v[0-9][^"]*\.tar\.gz(?=")' | head -n1)
if [[ -z "${TARBALL_PATH}" ]]; then
    error "No Linux x86_64 tarball found in the Development Releases section"
  fi

  TARBALL_URL="https://redream.io${TARBALL_PATH}"

  # Prepare the installation directory
  mkdir -p "${INSTALL_DIR}"

  # Download
  echo "[INFO] Downloading ${TARBALL_URL}..."
  curl -L "${TARBALL_URL}" -o "${TMP_DIR}/redream.tar.gz"

  # Extract
  echo "[INFO] Extracting the tarball..."
  mkdir -p "${TMP_DIR}/extract"
  tar -xzf "${TMP_DIR}/redream.tar.gz" -C "${TMP_DIR}/extract"

  mkdir -p "${INSTALL_DIR}/"
  mv "${TMP_DIR}/extract"/* "${INSTALL_DIR}/"
  chmod +x "${INSTALL_DIR}/redream"

  # Clean up
  rm -rf "${TMP_DIR}"
  echo "[INFO] Installation completed."
}

## ENTRY POINT
case "$1" in
"-i") tarball_install;;
"-u"|"-d") uninstall;;
*)  exit 1;;
esac

exit 0