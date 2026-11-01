#!/usr/bin/env bash
## SUPERMODEL INSTALLER
## Created: 30 July 2026
set -eo pipefail

## VARIABLES

RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. >/dev/null 2>&1 && pwd -P)"
source "${RETROBOX_ROOT}/tools/lib/paths.sh"
INSTALL_DIR="${RETROBOX_EMULATORS_DIR}/supermodel"
TMP_DIR="$(mktemp -d)"
REPO="trzy/Supermodel"
API_URL="https://api.github.com/repos/$REPO/releases"

## FUNCTIONS

function error() {
    echo "[ERROR] $*."
    exit 1
}

function uninstall() {
    if [[ -d "${INSTALL_DIR}" ]]; then
        rm -rf "${INSTALL_DIR}"
        echo "[INFO] Uninstallation completed."
    else
        echo "[INFO] The installation directory does not exist."
    fi
}

function install_supermodel(){
  # Check curl and jq
  if ! command -v curl &> /dev/null; then
    dnf install -y curl
  fi

  if ! command -v jq &> /dev/null; then
    dnf install -y jq
  fi

  response=$(curl -sL "${API_URL}?per_page=10")

  # Check that the response is a valid JSON array
  if ! echo "$response" | jq -e 'type == "array"' >/dev/null 2>&1; then
    error "The GitHub API did not return a valid array. Check the request rate limit or the repository URL."
  fi

  # Extract the URL of the Linux tar.gz
  TAR_URL=$(echo "$response" | jq -r '
    [.[0].assets[]? | select(.name | contains("linux.tar.gz")) | .browser_download_url] | .[0]
  ')

  if [[ -z "${TAR_URL}" || "${TAR_URL}" == "null" ]]; then
    error "No Linux tar.gz found in the latest available release."
  fi

  # Prepare the directories
  mkdir -p "${TMP_DIR}"
  mkdir -p "${INSTALL_DIR}"

  # Download and extract
  echo "[INFO] Downloading Supermodel..."
  curl -L "${TAR_URL}" -o "${TMP_DIR}/supermodel.tar.gz"

  echo "[INFO] Installing..."
  tar -xzf "${TMP_DIR}/supermodel.tar.gz" -C "${TMP_DIR}"

  # Move the contents, keeping the structure
  EXTRACTED_DIR=$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n1)
  if [[ -n "${EXTRACTED_DIR}" ]]; then
      cp -r "${EXTRACTED_DIR}"/* "${INSTALL_DIR}/"
  else
      error "Could not find the extracted directory."
  fi

  # Clean up
  rm -rf "${TMP_DIR}"
  echo "[INFO] Installation completed in ${INSTALL_DIR}."
}

## ENTRY POINT
case "$1" in
   "-i") install_supermodel;;
   "-u"|"-d") uninstall;;
    *)  exit 1;;
esac

exit 0
